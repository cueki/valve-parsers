import zlib
import struct
import traceback
from hashlib import md5
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Optional, BinaryIO, List, Tuple, Union, Any

# see: https://developer.valvesoftware.com/wiki/VPK_(file_format)

@dataclass
class VPKDirectoryEntry:
    """Metadata for a file entry within a VPK archive.

    Contains information needed to locate and extract the file data.

    Attributes:
        crc: CRC32 checksum of the file data.
        preload_bytes: Number of bytes stored inline in the directory.
        archive_index: Which archive file contains the data (0x7FFF = directory file).
        entry_offset: Byte offset within the archive file.
        entry_length: Size of the file data in bytes.
        preload_data: Inline data stored in the directory (if any).
    """
    crc: int
    preload_bytes: int
    archive_index: int
    entry_offset: int
    entry_length: int
    preload_data: Optional[bytes] = None

    @classmethod
    def from_file(cls, file: BinaryIO) -> 'VPKDirectoryEntry':
        data = struct.unpack('<IHHII', file.read(16))

        entry = cls(
            crc=data[0],
            preload_bytes=data[1],
            archive_index=data[2],
            entry_offset=data[3],
            entry_length=data[4]
        )

        if entry.preload_bytes > 0:
            entry.preload_data = file.read(entry.preload_bytes)

        terminator = struct.unpack('<H', file.read(2))[0]
        if terminator != 0xFFFF:
            print(f"VPK WARNING: Expected 0xFFFF terminator, got 0x{terminator:04X}")

        return entry


def _parse_vpk_path(filepath: str) -> Tuple[str, str, str]:
    """Parse a file path into VPK components (extension, directory, filename)."""
    filepath = filepath.replace('\\', '/')

    last_slash = filepath.rfind('/')
    if last_slash >= 0:
        directory = filepath[:last_slash]
        filename_ext = filepath[last_slash + 1:]
    else:
        directory = ' '
        filename_ext = filepath

    last_dot = filename_ext.rfind('.')
    if last_dot > 0:
        filename = filename_ext[:last_dot]
        extension = filename_ext[last_dot + 1:]
    else:
        filename = filename_ext
        extension = ' '

    return extension, directory, filename


def _read_null_string(file: BinaryIO) -> str:
    """Read a null-terminated ASCII string from a binary file."""
    chunk_size = 256
    buffer = bytearray()
    bad_result = bytearray()
    had_data = False

    while True:
        chunk = file.read(chunk_size)
        if not chunk:
            break

        null_pos = chunk.find(b'\x00')
        if null_pos != -1:
            had_data = had_data or (null_pos > 0)
            for i in range(null_pos):
                byte = chunk[i]
                if 32 <= byte <= 126:
                    buffer.append(byte)
                else:
                    bad_result.append(byte)
            file.seek(-(len(chunk) - null_pos - 1), 1)
            break
        else:
            had_data = True
            for byte in chunk:
                if 32 <= byte <= 126:
                    buffer.append(byte)
                else:
                    bad_result.append(byte)

    if had_data and not buffer:
        print(f"[VPK] All chars filtered, bad_result: {bad_result.hex()}")

    return buffer.decode("ascii")


class VPKFile:
    """A parser for Valve Package (VPK) files.

    VPK files are Valve's archive format used in Source engine games to store
    game assets like textures, models, sounds, and scripts.

    Args:
        vpk_path: Path to the VPK file. Can be a single .vpk file or a _dir.vpk file
                 for multi-file archives. Accepts str or Path objects.
        auto_parse: Whether to automatically parse the directory on initialization.
                   Defaults to True for convenience.

    Example:
        >>> vpk = VPKFile("pak01_dir.vpk")  # Auto-parses by default
        >>> files = vpk.list_files()
        >>> vpk.extract_file("materials/example.vmt", "output.vmt")
        >>>
        >>> # manual parsing if needed
        >>> vpk = VPKFile("pak01_dir.vpk", auto_parse=False)
        >>> vpk.parse_directory()
    """
    def __init__(self, vpk_path: Union[str, Path], auto_parse: bool = True):
        self.vpk_path = vpk_path
        self.directory: Dict[str, Dict[str, Dict[str, VPKDirectoryEntry]]] = {}
        self._setup_paths()
        self.header_and_tree_offset = 0
        self._parsed = False
        if not self.is_dir_vpk:
            self._calculate_header_and_tree_offset()
        if auto_parse:
            self.parse_directory()

    def _setup_paths(self):
        """Set up paths for VPK file(s) - determines if single or multi-file archive."""
        if self.vpk_path.endswith('_dir.vpk'):
            self.is_dir_vpk = True
            self.dir_path = self.vpk_path
            self.base_path = self.vpk_path[:-8]
        else:
            path_without_ext = str(Path(self.vpk_path).with_suffix(''))
            if path_without_ext[-3:].isdigit() and path_without_ext[-4] == '_':
                path_without_ext = path_without_ext[:-4]

            possible_dir_path = f"{path_without_ext}_dir.vpk"

            if Path(possible_dir_path).exists():
                self.is_dir_vpk = True
                self.dir_path = possible_dir_path
                self.base_path = path_without_ext
            else:
                self.is_dir_vpk = False
                self.dir_path = self.vpk_path
                self.base_path = str(Path(self.vpk_path).with_suffix(''))

    def parse_directory(self) -> 'VPKFile':
        """Parse the VPK directory structure to enable file operations.

        Must be called before using file listing, extraction, or patching methods.

        Returns:
            Self for method chaining.

        Raises:
            IOError: If the VPK file cannot be read.
            ValueError: If the VPK format is invalid.
        """
        with open(self.dir_path, 'rb') as f:
            tree_offset = struct.calcsize('<7I')
            f.seek(tree_offset)

            while True:
                extension = _read_null_string(f)
                if not extension:
                    break

                while True:
                    path = _read_null_string(f)
                    if not path:
                        break

                    while True:
                        filename = _read_null_string(f)
                        if not filename:
                            break

                        entry = VPKDirectoryEntry.from_file(f)

                        if extension not in self.directory:
                            self.directory[extension] = {}
                        if path not in self.directory[extension]:
                            self.directory[extension][path] = {}

                        self.directory[extension][path][filename] = entry
        self._parsed = True
        return self

    def _calculate_header_and_tree_offset(self) -> int:
        """Calculate offset for single-file VPK archives."""
        try:
            with open(self.dir_path, 'rb') as f:
                header = f.read(28)
                if len(header) != 28:
                    raise ValueError(f"Invalid VPK header: expected 28 bytes, got {len(header)}")

                tree_size = struct.unpack('<I', header[8:12])[0]
                self.header_and_tree_offset = 28 + tree_size
                return self.header_and_tree_offset
        except Exception as e:
            print(f"Error calculating header offset: {e}")
            return 0

    def get_archive_path(self, archive_index: int) -> str:
        if not self.is_dir_vpk:
            return self.vpk_path

        if archive_index == 0x7fff:
            return self.dir_path
        return f"{self.base_path}_{archive_index:03d}.vpk"

    def read_from_archive(self, archive_index: int, offset: int, size: int) -> Optional[bytes]:
        archive_path = self.get_archive_path(archive_index)
        try:
            with open(archive_path, 'rb') as f:
                adjusted_offset = offset + (self.header_and_tree_offset if not self.is_dir_vpk else 0)
                f.seek(adjusted_offset)
                return f.read(size)
        except (IOError, OSError) as e:
            print(f"Error reading from archive {archive_path}: {e}")
            return None

    def list_files(self, extension: Optional[str] = None, path: Optional[str] = None) -> List[str]:
        """List all files in the VPK archive.

        Args:
            extension: Filter files by extension (e.g., 'vtf', 'vmt'). Optional.
            path: Filter files by directory path. Optional.

        Returns:
            List of file paths within the archive.

        Example:
            >>> vpk.list_files(extension="vtf")  # All texture files
            >>> vpk.list_files(path="materials/models")  # Files in specific directory
        """
        self._ensure_parsed()
        files = []
        extensions = [extension] if extension else self.directory.keys()

        for ext in extensions:
            if ext not in self.directory:
                continue

            paths = [path] if path else self.directory[ext].keys()
            for p in paths:
                if p not in self.directory[ext]:
                    continue

                for filename in self.directory[ext][p]:
                    full_path = f"{p}/{filename}.{ext}" if p != " " else f"{filename}.{ext}"
                    files.append(full_path)

        return files

    def find_files(self, pattern: str) -> List[str]:
        """Find files matching a pattern.

        Args:
            pattern: Glob pattern to match against file paths.
                    Examples: "materials/*.vmt", "models/player/*"

        Returns:
            List of matching file paths.

        Example:
            >>> vpk.find_files("materials/*.vmt")  # All material files
            >>> vpk.find_files("models/player/*")  # All player model files
        """
        self._ensure_parsed()
        all_files = self.list_files()
        if pattern.endswith('/'):
            return [f for f in all_files if f.startswith(pattern)]
        return [f for f in all_files if Path(f).match(pattern)]

    def find_file_path(self, filename: str) -> Optional[str]:
        """Find the full path of a file by its name.

        Args:
            filename: Name of the file to search for (e.g., "example.vmt").

        Returns:
            Full path within the VPK if found, None otherwise.

        Example:
            >>> full_path = vpk.find_file_path("example.vmt")
            >>> # Returns something like "materials/models/example.vmt"
        """
        self._ensure_parsed()
        try:
            name, ext = filename.rsplit('.', 1)
        except ValueError:
            return None

        if ext not in self.directory:
            return None

        for path in self.directory[ext]:
            if name in self.directory[ext][path]:
                return f"{path}/{filename}" if path and path != " " else filename

        return None

    def _get_file_entry(self, filepath: str) -> Optional[Tuple[str, str, VPKDirectoryEntry]]:
        """Get raw directory entry for a file. Use get_file_info() for public API."""
        self._ensure_parsed()
        try:
            extension, directory, filename = _parse_vpk_path(filepath)

            if (extension in self.directory and
                    directory in self.directory[extension] and
                    filename in self.directory[extension][directory]):
                return extension, directory, self.directory[extension][directory][filename]
        except (AttributeError, KeyError) as e:
            print(f"Error getting file entry: {e}")
        return None

    def extract_file(self, filepath: str, output_path: str) -> bool:
        """Extract a file from the VPK archive to disk.

        Args:
            filepath: Path of the file within the VPK archive.
            output_path: Where to save the extracted file.

        Returns:
            True if extraction succeeded, False otherwise.

        Example:
            >>> success = vpk.extract_file("materials/example.vmt", "output.vmt")
            >>> if success:
            ...     print("File extracted successfully")
        """
        entry_info = self._get_file_entry(filepath)
        if not entry_info:
            return False

        extension, directory, entry = entry_info

        try:
            file_data = self.read_from_archive(entry.archive_index, entry.entry_offset, entry.entry_length)
            if not file_data:
                return False

            with open(output_path, 'wb') as f:
                if entry.preload_bytes > 0 and entry.preload_data:
                    f.write(entry.preload_data)
                f.write(file_data)

            return True
        except Exception as e:
            print(f"Error extracting file: {e}")
            return False

    def patch_file(self, filepath: str, new_data: bytes, create_backup: bool = False) -> bool:
        """Replace a file's contents within the VPK archive.

        Args:
            filepath: Path of the file within the VPK archive to replace.
            new_data: The new file contents as bytes.
            create_backup: Whether to create a backup of the original archive.
                          Backup will have .backup extension.

        Returns:
            True if patching succeeded, False otherwise.

        Note:
            The new data must be exactly the same size as the original file.

        Example:
            >>> with open("my_material.vmt", "rb") as f:
            ...     new_content = f.read()
            >>> success = vpk.patch_file("materials/example.vmt", new_content, create_backup=True)
        """
        entry_info = self._get_file_entry(filepath)
        if not entry_info:
            return False

        _, _, entry = entry_info

        try:
            if len(new_data) != entry.entry_length:
                raise ValueError(
                    f"Modified file {filepath} does not match original "
                    f"({len(new_data)} != {entry.entry_length} bytes)"
                )

            archive_path = self.get_archive_path(entry.archive_index)

            if create_backup:
                backup_path = f"{archive_path}.backup"
                if not Path(backup_path).exists():
                    with open(archive_path, 'rb') as src, open(backup_path, 'wb') as dst:
                        dst.write(src.read())

            with open(archive_path, 'rb+') as f:
                f.seek(entry.entry_offset)
                f.write(new_data)

            return True
        except Exception as e:
            print(f"Error patching file: {e}")
            return False

    @classmethod
    def create(cls, source_dir: str, output_base_path: str, split_size: int = None) -> bool:
        """Create a new VPK archive from a directory.

        Args:
            source_dir: Directory containing files to archive.
            output_base_path: Base path for the output VPK file(s).
                             For single files: "output.vpk" or "output"
                             For multi-file: "output" (will create output_dir.vpk, output_001.vpk, etc.)
            split_size: Maximum size per archive file in bytes. If None, creates a single file.
                       Example: 100*1024*1024 for 100MB splits.

        Returns:
            True if creation succeeded, False otherwise.

        Example:
            >>> # Single file
            >>> VPKFile.create("my_mod", "my_mod.vpk")
            >>>
            >>> # Multi-file with 100MB splits
            >>> VPKFile.create("my_mod", "my_mod", split_size=100*1024*1024)
        """
        source_path = Path(source_dir)
        base_output_path = Path(output_base_path)

        # pathlib.relative_to() is a little slow for this so im string slicing
        try:
            base_output_path.parent.mkdir(parents=True, exist_ok=True)
            source_str = str(source_path.absolute())

            if not source_str.endswith('/'):
                source_str += '/'
            source_len = len(source_str)

            files = []
            for f in source_path.rglob('*'):
                if f.is_file():
                    full_path_str = str(f.absolute())
                    rel_path_str = full_path_str[source_len:]
                    files.append((full_path_str, rel_path_str))

            if not files:
                print("No files found in source directory")
                return False

            vpk_structure = cls._build_vpk_structure(files)

            if split_size is None:
                # for single-file VPK use the provided path directly
                output_path = f"{base_output_path}.vpk" if not str(base_output_path).endswith('.vpk') else str(base_output_path)
                return cls._create_single_vpk(vpk_structure, output_path)
            else:
                # for multi-file VPK use _dir.vpk naming
                return cls._create_multi_vpk(vpk_structure, base_output_path, split_size)
        except Exception as e:
            print(f"Error creating VPK: {e}")
            traceback.print_exc()
            return False

    @staticmethod
    def _build_vpk_structure(files):
        """Build internal VPK directory structure from file list."""
        vpk_structure = {}
        for file_path, rel_path_str in files:
            extension, path, filename = _parse_vpk_path(rel_path_str)

            if extension not in vpk_structure:
                vpk_structure[extension] = {}
            if path not in vpk_structure[extension]:
                vpk_structure[extension][path] = {}

            with open(file_path, 'rb') as f:
                content = f.read()

            vpk_structure[extension][path][filename] = {
                'content': content,
                'size': len(content),
                'path': file_path
            }
        return vpk_structure

    @staticmethod
    def _write_vpk_header(f, tree_size=0, embed_chunk_length=0):
        """Write VPK header structure to file."""
        tree_size_pos = 8
        embed_chunk_length_pos = 12
        header = struct.pack('<7I', 0x55AA1234, 2, tree_size, embed_chunk_length, 0, 48, 0)
        f.write(header)
        return tree_size_pos, embed_chunk_length_pos

    @staticmethod
    def _write_directory_tree(f, vpk_structure, archive_entries=None):
        """Write VPK directory tree structure to file."""
        entry_positions = []
        archive_offset = 0

        structure = archive_entries if vpk_structure is None else vpk_structure

        for extension in sorted(structure.keys()):
            f.write(extension.encode('ascii') + b'\0')

            for path in sorted(structure[extension].keys()):
                f.write(path.encode('ascii') + b'\0')

                for filename in sorted(structure[extension][path].keys()):
                    f.write(filename.encode('ascii') + b'\0')

                    if archive_entries and vpk_structure is None:
                        entry = archive_entries[extension][path][filename]
                        f.write(struct.pack('<IHHII', entry['crc'], 0, entry['archive_idx'], entry['offset'], entry['size']))
                    else:
                        file_info = vpk_structure[extension][path][filename]
                        content = file_info['content']
                        crc = zlib.crc32(content) & 0xFFFFFFFF
                        entry_positions.append((f.tell() + 8, archive_offset, len(content)))
                        f.write(struct.pack('<IHHII', crc, 0, 0x7FFF, 0, len(content)))
                        archive_offset += len(content)

                    f.write(struct.pack('<H', 0xFFFF))

                f.write(b'\0')
            f.write(b'\0')
        f.write(b'\0')

        return entry_positions

    @staticmethod
    def _write_checksums(f, dir_start, dir_size):
        """Write MD5 checksums to VPK file."""
        tree_md5 = md5()
        f.seek(dir_start)
        tree_md5.update(f.read(dir_size))

        chunk_hashes_md5 = md5()
        file_md5 = md5()
        f.seek(0)
        header_data = f.read(dir_start)
        file_md5.update(header_data)
        file_md5.update(tree_md5.digest())
        file_md5.update(chunk_hashes_md5.digest())

        f.seek(0, 2)
        f.write(tree_md5.digest())
        f.write(chunk_hashes_md5.digest())
        f.write(file_md5.digest())

    @staticmethod
    def _create_single_vpk(vpk_structure, output_path):
        """Create a single-file VPK archive."""
        try:
            with open(output_path, 'w+b') as f:
                tree_size_pos, embed_chunk_length_pos = VPKFile._write_vpk_header(f)
                dir_start = f.tell()

                entry_positions = VPKFile._write_directory_tree(f, vpk_structure)

                dir_end = f.tell()
                dir_size = dir_end - dir_start
                data_start = f.tell()

                # write data and update offsets
                current_offset = 0
                for extension in sorted(vpk_structure.keys()):
                    for path in sorted(vpk_structure[extension].keys()):
                        for filename in sorted(vpk_structure[extension][path].keys()):
                            content = vpk_structure[extension][path][filename]['content']
                            f.write(content)

                embed_chunk_length = f.tell() - data_start

                for pos, offset, length in entry_positions:
                    f.seek(pos)
                    f.write(struct.pack('<I', current_offset))
                    current_offset += length

                VPKFile._write_checksums(f, dir_start, dir_size)

                f.seek(tree_size_pos)
                f.write(struct.pack('<I', dir_size))
                f.seek(embed_chunk_length_pos)
                f.write(struct.pack('<I', embed_chunk_length))

            return True
        except Exception as e:
            print(f"Error creating single-file VPK: {e}")
            return False

    @staticmethod
    def _create_multi_vpk(vpk_structure, base_output_path, split_size):
        """Create a multi-file VPK archive with size-based splitting."""
        try:
            archive_entries = {}
            current_archive_idx = 0
            current_size = 0
            current_archive_file = None
            current_archive_pos = 0

            try:
                for extension in sorted(vpk_structure.keys()):
                    for path in sorted(vpk_structure[extension].keys()):
                        for filename in sorted(vpk_structure[extension][path].keys()):
                            file_info = vpk_structure[extension][path][filename]
                            content = file_info['content']
                            size = file_info['size']

                            if current_size + size > split_size and current_size > 0:
                                if current_archive_file:
                                    current_archive_file.close()
                                current_archive_idx += 1
                                current_size = 0
                                current_archive_file = None

                            if current_archive_file is None:
                                archive_path = f"{base_output_path}_{current_archive_idx:03d}.vpk"
                                current_archive_file = open(archive_path, 'wb')
                                current_archive_pos = 0

                            crc = zlib.crc32(content) & 0xFFFFFFFF

                            if extension not in archive_entries:
                                archive_entries[extension] = {}
                            if path not in archive_entries[extension]:
                                archive_entries[extension][path] = {}

                            archive_entries[extension][path][filename] = {
                                'archive_idx': current_archive_idx,
                                'offset': current_archive_pos,
                                'size': size,
                                'crc': crc
                            }

                            current_archive_file.write(content)
                            current_archive_pos += size
                            current_size += size
            finally:
                if current_archive_file:
                    current_archive_file.close()

            # create directory file
            dir_path = f"{base_output_path}_dir.vpk"
            with open(dir_path, 'w+b') as dir_f:
                tree_size_pos, _ = VPKFile._write_vpk_header(dir_f)
                dir_start = dir_f.tell()

                VPKFile._write_directory_tree(dir_f, None, archive_entries)

                dir_end = dir_f.tell()
                dir_size = dir_end - dir_start

                VPKFile._write_checksums(dir_f, dir_start, dir_size)

                dir_f.seek(tree_size_pos)
                dir_f.write(struct.pack('<I', dir_size))

            return True
        except Exception as e:
            print(f"Error creating multi-file VPK: {e}")
            return False

    def _ensure_parsed(self) -> None:
        """Ensure directory has been parsed before use."""
        if not self._parsed:
            self.parse_directory()

    def extract_all(self, output_dir: str, pattern: Optional[str] = None) -> int | None:
        """Extract multiple files to a directory.

        Args:
            output_dir: Directory to extract files to.
            pattern: Optional glob pattern to filter files (e.g., "materials/*.vmt").
                    If None, extracts all files.

        Returns:
            Number of files successfully extracted.

        Example:
            >>> count = vpk.extract_all("extracted_files")
            >>> print(f"Extracted {count} files")
            >>>
            >>> # extract only material files
            >>> count = vpk.extract_all("materials", "materials/*.vmt")
        """
        self._ensure_parsed()
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        extracted = 0
        created_dirs = set()
        output_dir_str = str(output_path)

        files_to_extract = []
        if pattern:
            matching_files = set(self.find_files(pattern))
            for extension in self.directory:
                for directory in self.directory[extension]:
                    for filename, entry in self.directory[extension][directory].items():
                        filepath = f"{directory}/{filename}.{extension}" if directory != " " else f"{filename}.{extension}"
                        if filepath in matching_files:
                            files_to_extract.append((extension, directory, filename, entry))
        else:
            for extension in self.directory:
                for directory in self.directory[extension]:
                    for filename, entry in self.directory[extension][directory].items():
                        files_to_extract.append((extension, directory, filename, entry))

        files_to_extract.sort(key=lambda x: (x[3].archive_index, x[3].entry_offset))

        open_archives = {}
        try:
            for extension, directory, filename, entry in files_to_extract:
                try:
                    if directory != " ":
                        parent_dir = output_dir_str + '/' + directory
                        if parent_dir not in created_dirs:
                            Path(parent_dir).mkdir(parents=True, exist_ok=True)
                            created_dirs.add(parent_dir)
                        full_output_path = parent_dir + '/' + filename + '.' + extension
                    else:
                        full_output_path = output_dir_str + '/' + filename + '.' + extension

                    archive_path = self.get_archive_path(entry.archive_index)
                    if archive_path not in open_archives:
                        open_archives[archive_path] = open(archive_path, 'rb')

                    archive_file = open_archives[archive_path]
                    adjusted_offset = entry.entry_offset + (self.header_and_tree_offset if not self.is_dir_vpk else 0)
                    archive_file.seek(adjusted_offset)
                    file_data = archive_file.read(entry.entry_length)

                    with open(full_output_path, 'wb') as f:
                        if entry.preload_bytes > 0 and entry.preload_data:
                            f.write(entry.preload_data)
                        f.write(file_data)

                    extracted += 1
                except Exception as e:
                    print(f"Failed to extract file: {e}")
        finally:
            for archive_file in open_archives.values():
                archive_file.close()

        return extracted

    def get_file_data(self, filepath: str) -> Optional[bytes]:
        """Read a file's contents directly into memory.

        Args:
            filepath: Path of the file within the VPK archive.

        Returns:
            File contents as bytes, or None if file not found.

        Example:
            >>> data = vpk.get_file_data("materials/example.vmt")
            >>> if data:
            ...     content = data.decode('utf-8')  # for text files
        """
        self._ensure_parsed()
        entry_info = self._get_file_entry(filepath)
        if not entry_info:
            return None

        extension, directory, entry = entry_info

        try:
            file_data = self.read_from_archive(entry.archive_index, entry.entry_offset, entry.entry_length)
            if not file_data:
                return None

            # combine preload data with archive data
            result = bytearray()
            if entry.preload_bytes > 0 and entry.preload_data:
                result.extend(entry.preload_data)
            result.extend(file_data)

            return bytes(result)
        except Exception as e:
            print(f"Error reading file data: {e}")
            return None

    def file_exists(self, filepath: str) -> bool:
        """Check if a file exists in the VPK archive.

        Args:
            filepath: Path of the file within the VPK archive.

        Returns:
            True if the file exists, False otherwise.

        Example:
            >>> if vpk.file_exists("materials/example.vmt"):
            ...     print("File found!")
        """
        self._ensure_parsed()
        return self._get_file_entry(filepath) is not None

    def get_file_info(self, filepath: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive information about a file.

        Args:
            filepath: Path of the file within the VPK archive.

        Returns:
            Dictionary with file information or None if not found.
            Contains: 'size', 'crc', 'archive_index', 'offset', 'preload_bytes'

        Example:
            >>> info = vpk.get_file_info("materials/example.vmt")
            >>> if info:
            ...     print(f"Size: {info['size']} bytes")
            ...     print(f"CRC: 0x{info['crc']:08X}")
        """
        self._ensure_parsed()
        entry_info = self._get_file_entry(filepath)
        if not entry_info:
            return None

        extension, directory, entry = entry_info
        return {
            'size': entry.entry_length,
            'crc': entry.crc,
            'archive_index': entry.archive_index,
            'offset': entry.entry_offset,
            'preload_bytes': entry.preload_bytes,
            'extension': extension,
            'directory': directory
        }
