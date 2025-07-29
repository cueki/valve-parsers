# Valve Parsers

A Python library for parsing Valve game files, extracted from my casual-preloader project. This library provides support for:

- **VPK (Valve Package)** files - Valve's archive format used in Source engine games
- **PCF (Particle)** files - Valve's particle system files - **See constants.py for supported versions**

## Features

- Support for single-file and multi-file VPK archives (creation and modification)
- Full VPK directory parsing and file extraction
- In-place VPK file patching with size checking
- PCF parsing and encoding
- Support for all PCF attribute types (see constants.py for these as well)

## Installation

```bash
pip install valve-parsers
```

## Quick Start (Parsing + Modification)

### VPK Files

```python
from valve_parsers import VPKFile

# Open and parse a VPK file
vpk = VPKFile("path/to/archive.vpk").parse_directory()

# List all files
files = vpk.list_files()
print(f"Found {len(files)} files")

# Find specific files
texture_files = vpk.list_files(extension="vtf")
material_files = vpk.find_files("materials/*.vmt")

# Extract a file
vpk.extract_file("materials/models/player/scout.vmt", "output/scout.vmt")

# Get file information
entry_info = vpk.get_file_entry("scripts/game_sounds.txt")
if entry_info:
    extension, directory, entry = entry_info
    print(f"File size: {entry.entry_length} bytes")
    print(f"Archive index: {entry.archive_index}")
    
# Patch a file
# Read a new material file from disk
new_texture_path = "my_custom_material.vmt"
with open(new_texture_path, 'rb') as f:
    new_texture_data = f.read()

# Target file path inside the VPK
target_file = "materials/models/player/scout_red.vmt"

# Optionally create a backup before modification
vpk.patch_file(target_file, new_texture_data, create_backup=False)

```

### PCF Files

```python
from valve_parsers import PCFFile

# Open and decode a PCF file
pcf = PCFFile("path/to/particles.pcf").decode()

print(f"PCF Version: {pcf.version}")
print(f"String dictionary: {len(pcf.string_dictionary)} entries")
print(f"Elements: {len(pcf.elements)} particle systems")

# Print particle system data
for element in pcf.elements:
    print(f"Element: {element.element_name}")
    for attr_name, (attr_type, attr_value) in element.attributes.items():
        print(f"  {attr_name.decode()}: {attr_value}")
        
# Rename all operators to ''
for i, element in enumerate(pcf.elements):
    type_name = pcf.string_dictionary[element.type_name_index].decode('ascii')
    if type_name == 'DmeParticleOperator':
        element.element_name = str('').encode('ascii')

# Encode back to file
pcf.encode("output/modified_particles.pcf")
```

### Creating VPK Archives

```python
from valve_parsers import VPKFile

# Create a single-file VPK
success = VPKFile.create("source_directory", "output/archive.vpk")

# Create a multi-file VPK with size limit (100MB per archive spit)
success = VPKFile.create("source_directory", "output/archive", split_size=100*1024*1024)
```

## API Reference

### VPKFile

The main class for working with VPK archives.

#### Constructor
- `VPKFile(vpk_path: str)` - Initialize with path to VPK file

#### Methods
- `parse_directory() -> VPKFile` - Parse the VPK directory structure
- `list_files(extension: str = None, path: str = None) -> List[str]` - List files with optional filtering
- `find_files(pattern: str) -> List[str]` - Find files matching a glob pattern
- `find_file_path(filename: str) -> Optional[str]` - Find the full path of a filename
- `extract_file(filepath: str, output_path: str) -> bool` - Extract a file from the archive
- `patch_file(filepath: str, new_data: bytes, create_backup: bool = False) -> bool` - Modify a file in the archive
- `create(source_dir: str, output_base_path: str, split_size: int = None) -> bool` - Create new VPK archive

#### Properties
- `directory` - Parsed directory structure
- `is_dir_vpk` - Whether this is a directory VPK file
- `vpk_path` - Path to the VPK file

### VPKDirectoryEntry

Represents an entry in the VPK directory.

#### Properties
- `crc: int` - CRC32 checksum
- `preload_bytes: int` - Number of preload bytes
- `archive_index: int` - Archive file index
- `entry_offset: int` - Offset within archive
- `entry_length: int` - Length of file data
- `preload_data: Optional[bytes]` - Preloaded data

### PCFFile

The main class for working with PCF particle files.

#### Constructor
- `PCFFile(input_file: Union[Path, str], version: str = "DMX_BINARY2_PCF1")` - Initialize with file path, default version is "DMX_BINARY2_PCF1"

#### Methods
- `decode() -> PCFFile` - Parse the PCF file
- `encode(output_path: Union[Path, str]) -> PCFFile` - Write PCF file to disk

#### Properties
- `version` - PCF version string
- `string_dictionary` - List of strings used in the file
- `elements` - List of particle system elements

### PCFElement

Represents a particle system element.

#### Properties
- `type_name_index: int` - Index into string dictionary for type name
- `element_name: bytes` - Name of the element
- `data_signature: bytes` - 16-byte signature
- `attributes: Dict[bytes, Tuple[AttributeType, Any]]` - Element attributes

### Constants

- `PCFVersion` - Enum of supported PCF versions
- `AttributeType` - Enum of PCF attribute types

## Supported Games

This library works with VPK and PCF files from Orange Box titles. 
Mostly intended for TF2, YMMV with other games.

See: 

https://developer.valvesoftware.com/wiki/PCF 

https://developer.valvesoftware.com/wiki/VPK_(file_format)

## License

MIT License - See LICENSE file for details.

## Contributing

This library was extracted from my casual-pre-loader project. Contributions are welcome!

## Changelog
### 1.0.2
- Single file VPK no longer has _dir name
### 1.0.1
- Nothing
### 1.0.0
- Initial release
- VPK parsing and creation support
- PCF parsing and encoding support
