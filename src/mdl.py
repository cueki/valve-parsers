import struct
from pathlib import Path
from typing import List, Union

from ._io import read_cstring_at, read_fixed_string

# see: https://developer.valvesoftware.com/wiki/MDL_(Source)


_MDL_ID = b"IDST"
_SUPPORTED_VERSIONS = range(44, 50)

# header field offsets
_OFF_ID = 0
_OFF_VERSION = 4
_OFF_CHECKSUM = 8
_OFF_NAME = 12  # char[64]
_OFF_DATA_LENGTH = 76
_OFF_MATERIAL_COUNT = 204
_OFF_MATERIAL_OFFSET = 208
_OFF_MATERIAL_DIR_COUNT = 212
_OFF_MATERIAL_DIR_OFFSET = 216

# each material entry is 4(nameIndex) + 4(flags) + 4(used) + 13*4(unused) = 64 bytes,
# with nameIndex relative to the start of that entry.
_MATERIAL_ENTRY_SIZE = 64


class MDLFile:
    """A (tiny) parser for Source engine MDL (model) files.

    Currently scoped to reading the materials[] and materialDirectories[]
    blocks, and rewriting materialDirectories[] in place using a
    append, the new strings are appended at EOF, the int32
    offset table is repointed at them, and dataLength is updated.

    Args:
        mdl_path: Path to the MDL file. Accepts str or Path objects.
        auto_parse: Whether to automatically parse on initialization.
                   Defaults to True for convenience.

    Example:
        >>> mdl = MDLFile("path/to/model.mdl")
        >>> print(mdl.materials)         # ['my_texture', 'my_texture_blue']
        >>> print(mdl.material_dirs)     # ['models\\\\player\\\\demo\\\\']
        >>> mdl.rewrite_material_dirs(['console\\\\models\\\\player\\\\demo\\\\'])
    """

    def __init__(self, mdl_path: Union[str, Path], auto_parse: bool = True):
        self.mdl_path = str(mdl_path)
        self.version: int = 0
        self.checksum: int = 0
        self.name: str = ""
        self.data_length: int = 0
        self.file_size: int = 0
        self.materials: List[str] = []
        self.material_dirs: List[str] = []
        self._material_offset: int = 0
        self._material_dir_offset: int = 0
        self._parsed = False
        if auto_parse:
            self.parse()

    def parse(self) -> "MDLFile":
        """Parse the MDL header and populate materials / material_dirs.

        Returns:
            Self for method chaining.

        Raises:
            ValueError: If the file is not an MDL or is an unsupported version.
        """
        buf = Path(self.mdl_path).read_bytes()

        if buf[_OFF_ID:_OFF_ID + 4] != _MDL_ID:
            raise ValueError(f"not an MDL file: {self.mdl_path}")

        (version,) = struct.unpack_from("<i", buf, _OFF_VERSION)
        if version not in _SUPPORTED_VERSIONS:
            raise ValueError(f"unsupported MDL version {version} in {self.mdl_path}")

        (checksum,) = struct.unpack_from("<i", buf, _OFF_CHECKSUM)
        name = read_fixed_string(buf, _OFF_NAME, 64)
        (data_length,) = struct.unpack_from("<i", buf, _OFF_DATA_LENGTH)

        (mat_count,) = struct.unpack_from("<i", buf, _OFF_MATERIAL_COUNT)
        (mat_offset,) = struct.unpack_from("<i", buf, _OFF_MATERIAL_OFFSET)
        (dir_count,) = struct.unpack_from("<i", buf, _OFF_MATERIAL_DIR_COUNT)
        (dir_offset,) = struct.unpack_from("<i", buf, _OFF_MATERIAL_DIR_OFFSET)

        # materials is an array of 64-byte entries
        materials: List[str] = []
        for i in range(mat_count):
            entry_pos = mat_offset + i * _MATERIAL_ENTRY_SIZE
            (name_rel,) = struct.unpack_from("<i", buf, entry_pos)
            materials.append(read_cstring_at(buf, entry_pos + name_rel))

        # materialDirectories is array of int32 absolute offsets to null-terminated strings
        material_dirs: List[str] = []
        for i in range(dir_count):
            (str_off,) = struct.unpack_from("<i", buf, dir_offset + i * 4)
            material_dirs.append(read_cstring_at(buf, str_off))

        self.version = version
        self.checksum = checksum
        self.name = name
        self.data_length = data_length
        self.file_size = len(buf)
        self.materials = materials
        self.material_dirs = material_dirs
        self._material_offset = mat_offset
        self._material_dir_offset = dir_offset
        self._parsed = True
        return self

    def rewrite_material_dirs(
        self,
        new_dirs: List[str],
        *,
        update_data_length: bool = True,
    ) -> None:
        """Replace materialDirectories[] with new_dirs.

        Appends each new string at EOF. When `len(new_dirs) == dir_count`, the
        existing int32 offset table is overwritten in place. When the lengths
        differ (growing or shrinking), a fresh int32 table is appended at EOF
        and the header's count + offset fields are updated to point at it; the
        old table bytes become orphaned.

        Args:
            new_dirs: Replacement material directories. Length may differ from
                the existing materialDirectories[].
            update_data_length: Whether to update the dataLength header field
                to match the new file size. Defaults to True.

        Raises:
            ValueError: If the file is no longer a valid MDL.
        """
        self._ensure_parsed()
        buf = bytearray(Path(self.mdl_path).read_bytes())

        if buf[_OFF_ID:_OFF_ID + 4] != _MDL_ID:
            raise ValueError(f"not an MDL file: {self.mdl_path}")

        (dir_count,) = struct.unpack_from("<i", buf, _OFF_MATERIAL_DIR_COUNT)
        (dir_offset,) = struct.unpack_from("<i", buf, _OFF_MATERIAL_DIR_OFFSET)

        new_offsets: List[int] = []
        for s in new_dirs:
            new_offsets.append(len(buf))
            buf.extend(s.encode("ascii") + b"\x00")

        if len(new_dirs) == dir_count:
            for i, new_off in enumerate(new_offsets):
                struct.pack_into("<i", buf, dir_offset + i * 4, new_off)
            new_dir_offset = dir_offset
        else:
            new_dir_offset = len(buf)
            for new_off in new_offsets:
                buf.extend(struct.pack("<i", new_off))
            struct.pack_into("<i", buf, _OFF_MATERIAL_DIR_COUNT, len(new_dirs))
            struct.pack_into("<i", buf, _OFF_MATERIAL_DIR_OFFSET, new_dir_offset)

        if update_data_length:
            struct.pack_into("<i", buf, _OFF_DATA_LENGTH, len(buf))

        Path(self.mdl_path).write_bytes(buf)

        self.material_dirs = list(new_dirs)
        self._material_dir_offset = new_dir_offset
        self.file_size = len(buf)
        if update_data_length:
            self.data_length = len(buf)

    def rewrite_materials(
        self,
        new_materials: List[str],
        *,
        update_data_length: bool = True,
    ) -> None:
        """Replace per-material name strings in place.

        Appends each new string at EOF and rewrites each material entry's
        nameIndex (int32, relative to that entry's own start). No existing
        bytes are shifted, so all other offsets in the file remain valid.

        Useful when relocating model materials on disk: some MDLs are
        compiled with `$cdmaterials` blank and the full path baked into the
        material name itself (yielding an empty material_dir entry paired
        with a path-rooted name like `models/foo/bar`). Moving the on-disk
        folder requires re-prefixing those names too.

        Args:
            new_materials: Replacement material name strings. Must have the
                same length as the existing materials[].
            update_data_length: Whether to update the dataLength header field
                to match the new file size. Defaults to True.

        Raises:
            ValueError: If new_materials length doesn't match the existing
                count, or if the file is no longer a valid MDL.
        """
        self._ensure_parsed()
        buf = bytearray(Path(self.mdl_path).read_bytes())

        if buf[_OFF_ID:_OFF_ID + 4] != _MDL_ID:
            raise ValueError(f"not an MDL file: {self.mdl_path}")

        (mat_count,) = struct.unpack_from("<i", buf, _OFF_MATERIAL_COUNT)
        (mat_offset,) = struct.unpack_from("<i", buf, _OFF_MATERIAL_OFFSET)

        if len(new_materials) != mat_count:
            raise ValueError(
                f"new_materials has {len(new_materials)} entries but MDL has {mat_count}"
            )

        for i, name in enumerate(new_materials):
            entry_pos = mat_offset + i * _MATERIAL_ENTRY_SIZE
            new_off = len(buf)
            buf.extend(name.encode("ascii") + b"\x00")
            struct.pack_into("<i", buf, entry_pos, new_off - entry_pos)

        if update_data_length:
            struct.pack_into("<i", buf, _OFF_DATA_LENGTH, len(buf))

        Path(self.mdl_path).write_bytes(buf)

        self.materials = list(new_materials)
        self.file_size = len(buf)
        if update_data_length:
            self.data_length = len(buf)

    def _ensure_parsed(self) -> None:
        if not self._parsed:
            self.parse()
