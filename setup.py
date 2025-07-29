from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="valve-parsers",
    version="1.0.2",
    author="Madison Lovett",
    description="Python library for parsing Valve game files (VPK and PCF)",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/cueki/valve-parsers",
    packages=["valve_parsers"],
    package_dir={"valve_parsers": "src"},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Games/Entertainment",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Archiving"
    ],
    python_requires=">=3.8",
    keywords="valve vpk pcf particle steam source engine team fortress tf2 half-life parser archive modding",
    project_urls={
        "Bug Reports": "https://github.com/cueki/valve-parsers/issues",
        "Source": "https://github.com/cueki/valve-parsers",
    },
)
