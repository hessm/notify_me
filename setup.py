import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="notify_me",
    version="0.0.1",
    author="Mark Hess",
    author_email="author@example.com",
    description="Get notified on discord when a topic of interest triggers",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/hessm/notify_me",
    packages=setuptools.find_packages(),
    install_requires=["lxml", "discord", "python-dotenv", "boto3"],
    extras_require={
        "dev":  ["black", "mypy", "importanize", "bumpversion"],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)
