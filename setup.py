import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="matcho",
    version="0.3.4",
    author="Martin Billinger-Finke",
    packages=["matcho"],
    description="A pattern matching and template library.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/mbillingr/matcho",
    license="LICENSE",
    python_requires=">=3.7",
)
