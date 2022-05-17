from setuptools import setup

setup(
    name="twillight_client",
    version="0.1",
    author="Saar Tochner",
    author_email="saar.tochner@gmail.com",
    description="privacy in PCNs",
    keywords="privacy lightning bitcoin",
    install_requires=['ECPy'],
    packages=['src'],
    classifiers=[
        "Development Status :: 3 - Alpha",
    ],
)
