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

### Creating VPK Archives

```python
from valve_parsers import VPKFile

# Create a single-file VPK
success = VPKFile.create("source_directory", "output/archive.vpk")

# Create a multi-file VPK with size limit (100MB per archive split)
success = VPKFile.create("source_directory", "output/archive", split_size=100*1024*1024)
```

### Working with VPK Archives

```python
from valve_parsers import VPKFile

# Open a VPK file
vpk = VPKFile("path/to/archive.vpk")

# List all files
files = vpk.list_files()
print(f"Found {len(files)} files")

# Find files matching a pattern
texture_files = vpk.list_files(extension="vtf")
material_files = vpk.find_files("materials/*.vmt")

# Extract a file
vpk.extract_file("materials/models/player/scout.vmt", "output/scout.vmt")

# Or load it directly into memory
file_data = vpk.get_file_data("materials/models/player/scout.vmt")
if file_data:
    content = file_data.decode('utf-8')
    
# Patch a file
# Read a new material file from disk
new_texture_path = "custom_scout_red.vmt"
with open(new_texture_path, 'rb') as f:
    new_texture_data = f.read()

# Target file path inside the VPK
target_file = "materials/models/player/scout_red.vmt"

# Check if a file exists
if vpk.file_exists(target_file):
    print("File found!")
    # Get file info
    info = vpk.get_file_info(target_file)
    if info:
        print(f"Size: {info['size']} bytes, CRC: 0x{info['crc']:08X}")
        # IMPORTANT: Patched files must match original size exactly!
        original_size = info['size']
        if len(new_texture_data) != original_size:
            if len(new_texture_data) < original_size:
                # Pad with spaces to match original size
                padding_needed = original_size - len(new_texture_data)
                print(f"Adding {padding_needed} bytes of padding")
                new_texture_data = new_texture_data + b' ' * padding_needed
            else:
                print(f"ERROR: New file is {len(new_texture_data) - original_size} bytes larger!")
                print("File cannot be patched - size must match exactly")
    
        # Now patch the file
        vpk.patch_file(target_file, new_texture_data, create_backup=False)

# Extract all files matching a pattern
count = vpk.extract_all("output_dir", pattern="materials/*.vmt")
print(f"Extracted {count} material files")
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

# Find a specific element by name
element = pcf.find_element_by_name("my_explosion_effect")
if element:
    print(f"Found element with {len(element.attributes)} attributes")

# Get all elements of a specific type
operators = pcf.get_elements_by_type('DmeParticleOperator')
print(f"Found {len(operators)} operators")

# Get and set attribute values with helper methods
from valve_parsers import AttributeType

element = pcf.find_element_by_name("my_effect")
if element:
    # Get attribute value
    radius = pcf.get_attribute_value(element, "radius", default=5.0)
    print(f"Current radius: {radius}")

    # Set attribute value
    pcf.set_attribute_value(element, "radius", 10.0, AttributeType.FLOAT)
    pcf.set_attribute_value(element, "color", (255, 0, 0, 255), AttributeType.COLOR)

pcf.encode("output/modified_particles.pcf")
```

## API Reference

### VPKFile

The main class for working with VPK archives.

#### Constructor
- `VPKFile(vpk_path: Union[str, Path], auto_parse: bool = True)` - Initialize with path to VPK file
  - `vpk_path`: Path to the VPK file
  - `auto_parse`: Automatically parse directory on init (default: True)

#### Methods
- `parse_directory() -> VPKFile` - Parse the VPK directory structure (called automatically unless `auto_parse=False`)
- `list_files(extension: str = None, path: str = None) -> List[str]` - List files with optional filtering
- `find_files(pattern: str) -> List[str]` - Find files matching a glob pattern
- `find_file_path(filename: str) -> Optional[str]` - Find the full path of a filename
- `extract_file(filepath: str, output_path: str) -> bool` - Extract a file from the archive
- `extract_all(output_dir: str, pattern: str = None) -> int` - Extract multiple files to a directory
- `patch_file(filepath: str, new_data: bytes, create_backup: bool = False) -> bool` - Modify a file in the archive
- `get_file_data(filepath: str) -> Optional[bytes]` - Read a file's contents directly into memory
- `file_exists(filepath: str) -> bool` - Check if a file exists in the archive
- `get_file_info(filepath: str) -> Optional[Dict]` - Get comprehensive information about a file
- `create(source_dir: str, output_base_path: str, split_size: int = None) -> bool` - Create new VPK archive (class method)

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
- `find_element_by_name(name: str) -> Optional[PCFElement]` - Find a particle element by its name
- `get_elements_by_type(type_name: str) -> List[PCFElement]` - Get all elements of a specific type
- `get_attribute_value(element: PCFElement, attr_name: str, default=None)` - Get an attribute value from an element (static method)
- `set_attribute_value(element: PCFElement, attr_name: str, value, attr_type: AttributeType)` - Set an attribute value on an element

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

## Contributing

This library was yoinked from my casual-pre-loader project. Contributions are welcome!

## Changelog
### 1.0.6
- Updated README with corrected examples
- Added documentation for all VPK methods: extract_all(), get_file_data(), file_exists(), get_file_info()
- Added file patching size-checking examples
- Made get_file_entry() private
- Cleaned up internal method documentation
### 1.0.5
- Auto-parse support
- Reading and writing is now 2-3x faster
### 1.0.2
- Single file VPK no longer has _dir name
### 1.0.1
- Nothing
### 1.0.0
- Initial release
- VPK parsing and creation support
- PCF parsing and encoding support
