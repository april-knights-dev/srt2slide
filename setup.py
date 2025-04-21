from setuptools import setup, find_packages

setup(
    name="movie2slidetxt",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "streamlit==1.32.2",
        "openai==1.75.0",
        "python-dotenv==1.0.1",
        "pyyaml==6.0.1",
        "srt==3.5.3",
        "typing-extensions>=4.5.0",
        "aiohttp>=3.8.0",
        "requests>=2.31.0",
        "python-dateutil>=2.8.2",
    ],
    python_requires=">=3.11",
) 