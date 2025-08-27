import struct
from pathlib import Path
from dataclasses import dataclass
from typing import BinaryIO, Any, List, Dict, Tuple, Union, Optional
from .constants import PCFVersion, AttributeType, ATTRIBUTE_VALUES

# see: https://developer.valvesoftware.com/wiki/PCF

@dataclass
class PCFElement:
    """Represents a particle system element in a PCF file.
    
    Each element contains attributes that define particle behavior,
    appearance, and other properties.
    
    Attributes:
        type_name_index: Index into the string dictionary for the element type.
        element_name: Name of this specific element instance.
        data_signature: 16-byte signature for data integrity.
        attributes: Dictionary mapping attribute names to (type, value) tuples.
    """
    type_name_index: int
    element_name: bytes
    data_signature: bytes
    attributes: Dict[bytes, Tuple[AttributeType, Any]]


@dataclass
class PCFFile:
    """Parser for Valve's PCF (Particle Cache File) format.
    
    PCF files define particle systems used in Source engine games.
    They contain particle effects like smoke, fire, explosions, etc.
    
    Args:
        input_file: Path to the PCF file to parse.
        version: PCF format version. Defaults to "DMX_BINARY2_PCF1".
                Available versions are in the PCFVersion enum.
    
    Example:
        >>> pcf = PCFFile("particles.pcf")
        >>> pcf.decode()
        >>> print(f"Found {len(pcf.elements)} particle systems")
        >>> pcf.encode("modified_particles.pcf")
    """
    def __init__(self, input_file: Union[Path, str], version: str = "DMX_BINARY2_PCF1"):
        self.version = version
        self.string_dictionary: List[bytes] = []
        self.elements: List[PCFElement] = []
        self.input_file = Path(input_file)

    @staticmethod
    def read_null_terminated_string(file: BinaryIO):
        """Read a null-terminated string from a binary file.
        
        Args:
            file: File object to read from.
            
        Returns:
            The string as bytes (excluding the null terminator).
        """
        chars = bytearray()
        while True:
            char = file.read(1)
            if not char or char == b'\x00':
                break
            chars.extend(char)
        return bytes(chars)

    @staticmethod
    def write_null_terminated_string(file: BinaryIO, string: Union[str, bytes]):
        """Write a null-terminated string to a binary file.
        
        Args:
            file: File object to write to.
            string: String to write (str or bytes). Strings are encoded as ASCII.
        """
        if isinstance(string, str):
            encoded = string.encode('ascii', errors='replace')
        else:
            encoded = string
        file.write(encoded + b'\x00')

    def write_attribute_data(self, file: BinaryIO, attr_type: AttributeType, value: Any) -> None:
        """Write attribute data to file in the correct format.
        
        Args:
            file: File object to write to.
            attr_type: Type of the attribute (from AttributeType enum).
            value: The value to write.
            
        Raises:
            ValueError: If the attribute type is unsupported.
        """
        if not ATTRIBUTE_VALUES.get(attr_type):
            raise ValueError(f"Unsupported attribute type: {attr_type}")

        if attr_type == AttributeType.STRING:
            if isinstance(value, str):
                value = value.encode('ascii', errors='replace')

            self.write_null_terminated_string(file, value)
            return

        if attr_type == AttributeType.MATRIX:
            for row in value:
                file.write(struct.pack(ATTRIBUTE_VALUES.get(attr_type), *row))
            return

        if attr_type.value >= AttributeType.ELEMENT_ARRAY.value:
            file.write(struct.pack(ATTRIBUTE_VALUES.get(attr_type), len(value)))
            base_type = AttributeType(attr_type.value - 14)
            for item in value:
                self.write_attribute_data(file, base_type, item)
            return

        if attr_type in [AttributeType.COLOR, AttributeType.VECTOR2, AttributeType.VECTOR3, AttributeType.VECTOR4]:
            file.write(struct.pack(ATTRIBUTE_VALUES.get(attr_type), *value))
            return

        file.write(struct.pack(ATTRIBUTE_VALUES.get(attr_type), value))

    def read_attribute_data(self, file: BinaryIO, attr_type: AttributeType):
        """Read attribute data from file based on type.
        
        Args:
            file: File object to read from.
            attr_type: Expected type of the attribute.
            
        Returns:
            The parsed attribute value in the appropriate Python type.
            
        Raises:
            ValueError: If the attribute type is unsupported.
        """
        if attr_type in [AttributeType.ELEMENT, AttributeType.INTEGER, AttributeType.FLOAT]:
            return struct.unpack(ATTRIBUTE_VALUES.get(attr_type), file.read(4))[0]

        if attr_type == AttributeType.BOOLEAN:
            return bool(file.read(1)[0])

        if attr_type == AttributeType.STRING:
            return self.read_null_terminated_string(file)

        if attr_type == AttributeType.BINARY:
            length = struct.unpack(ATTRIBUTE_VALUES.get(attr_type), file.read(4))[0]
            return file.read(length)

        if attr_type == AttributeType.COLOR:
            return struct.unpack('<4B', file.read(4))

        if attr_type == AttributeType.VECTOR2:
            return struct.unpack('<2f', file.read(8))

        if attr_type == AttributeType.VECTOR3:
            return struct.unpack('<3f', file.read(12))

        if attr_type == AttributeType.VECTOR4:
            return struct.unpack('<4f', file.read(16))

        if attr_type == AttributeType.MATRIX:
            return [struct.unpack('<4f', file.read(16)) for _ in range(4)]

        if attr_type.value >= AttributeType.ELEMENT_ARRAY.value:
            count = struct.unpack('<I', file.read(4))[0]
            base_type = AttributeType(attr_type.value - 14)
            return [self.read_attribute_data(file, base_type) for _ in range(count)]

        raise ValueError(f"Unsupported attribute type: {attr_type}")

    def encode(self, output_path: Union[Path, str]) -> 'PCFFile':
        """Write the PCF data to a file.
        
        Args:
            output_path: Where to save the PCF file.
            
        Returns:
            Self for method chaining.
            
        Raises:
            IOError: If the output file cannot be written.
            
        Example:
            >>> pcf.encode("modified_particles.pcf")
        """
        with open(output_path, 'wb') as file:
            # write header
            version_string = getattr(PCFVersion, self.version)
            self.write_null_terminated_string(file, f"{version_string}\n")

            # write string dictionary
            file.write(struct.pack('<H', len(self.string_dictionary)))

            # write strings as raw bytes
            for string in self.string_dictionary:
                file.write(string + b'\x00')

            # write element dictionary
            file.write(struct.pack('<I', len(self.elements)))
            for element in self.elements:
                file.write(struct.pack('<H', element.type_name_index))
                file.write(element.element_name + b'\x00')
                file.write(element.data_signature)

            # write element data
            for element in self.elements:
                file.write(struct.pack('<I', len(element.attributes)))
                for attr_name, (attr_type, attr_value) in element.attributes.items():
                    name_index = self.string_dictionary.index(attr_name)
                    file.write(struct.pack('<H', name_index))
                    file.write(struct.pack('B', attr_type))
                    self.write_attribute_data(file, attr_type, attr_value)

        return self

    def decode(self):
        """Parse the PCF file and populate string dictionary and elements.
        
        Returns:
            Self for method chaining.
            
        Raises:
            IOError: If the file cannot be read.
            ValueError: If the PCF format version is unsupported.
            
        Example:
            >>> pcf = PCFFile("particles.pcf").decode()
            >>> for element in pcf.elements:
            ...     print(f"Particle system: {element.element_name}")
        """
        with open(self.input_file, 'rb') as file:
            # read header
            header = self.read_null_terminated_string(file)
            header_str = header.decode('ascii', errors='replace')

            for ver_attr in dir(PCFVersion):
                if ver_attr.startswith('DMX_'):
                    version = getattr(PCFVersion, ver_attr)
                    if header_str == f"{version}\n":
                        self.version = ver_attr
                        break
            else:
                raise ValueError(f"Unsupported PCF version: {header}")

            # read string dictionary
            count = struct.unpack('<H', file.read(2))[0]

            # store strings as bytes
            for _ in range(count):
                string = self.read_null_terminated_string(file)
                self.string_dictionary.append(string)

            # read element dictionary
            element_count = struct.unpack('<I', file.read(4))[0]
            for _ in range(element_count):
                type_name_index = struct.unpack('<H', file.read(2))[0]
                element_name = self.read_null_terminated_string(file)
                data_signature = file.read(16)

                element = PCFElement(
                    type_name_index=type_name_index,
                    element_name=element_name,
                    data_signature=data_signature,
                    attributes={}
                )
                self.elements.append(element)

            # read element data
            for element in self.elements:
                attribute_count = struct.unpack('<I', file.read(4))[0]
                for _ in range(attribute_count):
                    type_name_index = struct.unpack('<H', file.read(2))[0]
                    attr_type = AttributeType(file.read(1)[0])

                    attr_name = self.string_dictionary[type_name_index]
                    attr_value = self.read_attribute_data(file, attr_type)
                    element.attributes[attr_name] = (attr_type, attr_value)

        return self

    def find_element_by_name(self, name: str) -> Optional[PCFElement]:
        """Find a particle element by its name.
        
        Args:
            name: Name of the element to find.
            
        Returns:
            The PCFElement if found, None otherwise.
            
        Example:
            >>> element = pcf.find_element_by_name("my_explosion_effect")
            >>> if element:
            ...     print(f"Found element with {len(element.attributes)} attributes")
        """
        name_bytes = name.encode('ascii', errors='replace')
        for element in self.elements:
            if element.element_name == name_bytes:
                return element
        return None

    def get_elements_by_type(self, type_name: str) -> List[PCFElement]:
        """Get all elements of a specific type.
        
        Args:
            type_name: Type name to search for (e.g., 'DmeParticleSystem', 'DmeParticleOperator').
            
        Returns:
            List of matching elements.
            
        Example:
            >>> operators = pcf.get_elements_by_type('DmeParticleOperator')
        """
        type_bytes = type_name.encode('ascii', errors='replace')
        results = []
        
        for element in self.elements:
            element_type = self.string_dictionary[element.type_name_index]
            if element_type == type_bytes:
                results.append(element)
                
        return results

    @staticmethod
    def get_attribute_value(element: PCFElement, attr_name: str, default=None):
        """Get an attribute value from an element with type conversion.
        
        Args:
            element: The PCFElement to read from.
            attr_name: Name of the attribute.
            default: Default value if attribute not found.
            
        Returns:
            The attribute value, or default if not found.
            
        Example:
            >>> element = pcf.find_element_by_name("my_effect")
            >>> if element:
            ...     radius = pcf.get_attribute_value(element, "radius", 5.0)
            ...     color = pcf.get_attribute_value(element, "color", (255, 255, 255, 255))
        """
        attr_bytes = attr_name.encode('ascii', errors='replace')
        if attr_bytes in element.attributes:
            attr_type, attr_value = element.attributes[attr_bytes]
            return attr_value
        return default

    def set_attribute_value(self, element: PCFElement, attr_name: str, value, attr_type: AttributeType):
        """Set an attribute value on an element.
        
        Args:
            element: The PCFElement to modify.
            attr_name: Name of the attribute.
            value: New value for the attribute.
            attr_type: Type of the attribute (from AttributeType enum).
            
        Example:
            >>> from valve_parsers import AttributeType
            >>> element = pcf.find_element_by_name("my_effect")
            >>> if element:
            ...     pcf.set_attribute_value(element, "radius", 10.0, AttributeType.FLOAT)
            ...     pcf.set_attribute_value(element, "color", (255, 0, 0, 255), AttributeType.COLOR)
        """
        attr_bytes = attr_name.encode('ascii', errors='replace')
        
        # add attribute name to string dictionary if not present
        if attr_bytes not in self.string_dictionary:
            self.string_dictionary.append(attr_bytes)
            
        element.attributes[attr_bytes] = (attr_type, value)