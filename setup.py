import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="cocotb-usb",
    version="0.0.1",
    author="Antmicro",
    author_email="contact@antmicro.com",
    description="Library for testing USB devices with cocotb",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/antmicro/usb-test-suite-cocotb-usb",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
         ],
    python_requires='>=3.6',
)
