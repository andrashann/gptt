import pathlib
from setuptools import setup

# The directory containing this file
HERE = pathlib.Path(__file__).parent

# The text of the README file
README = (HERE / "README.md").read_text()

# This call to setup() does all the work
setup(
    name="gptt",
    version="0.1.0",
    description="Download organized timetable information from the Google Directions API Transit mode for pretty output",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/andrashann/gptt",
    author="András Hann",
    author_email="dev@hann.io",
    license="Apache License 2.0",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Programming Language :: Python :: 3",
        "Environment :: Console",
        "License :: OSI Approved :: Apache Software License",
        "Topic :: Scientific/Engineering :: GIS",
        "Topic :: Utilities"
    ],
    include_package_data = True,
    packages=["gptt"],
    install_requires=["requests", "python-dateutil", "Jinja2"],
    entry_points={
        "console_scripts": [
            "gptt=gptt.__main__:main",
        ]
    },
)