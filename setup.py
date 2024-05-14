from setuptools import setup, find_packages

setup(
    name="generate_context",
    version="0.1",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "generate_context=generate_context.main:main",
        ],
    },
    install_requires=[
        # List any dependencies here, e.g., 'requests', 'pandas'
    ],
    author="Your Name",
    author_email="your.email@example.com",
    description="A tool to generate context files from a repository",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/generate_context",  # Replace with your actual URL
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
)
