from setuptools import setup, find_packages

DEPS = [
    # GUI
    "PyQt5>=5.15,<5.16",
    "pyqtgraph>=0.13,<0.14",
    "qdarkstyle==2.7",
    "qimage2ndarray>=1.10,<1.11",

    # numerical stack
    "numpy==1.23.5",
    "scipy>=1.10,<1.11",
    "numba>=0.57,<0.58",
    "pandas>=1.5,<1.6",

    # image and video
    "scikit-image>=0.20,<0.21",
    "Pillow>=9.5,<10",
    "imageio>=2.31,<2.32",
    "imageio-ffmpeg>=0.4,<0.5",
    "opencv-python>=4.8,<4.9",

    # data, versioning, hardware
    "tables>=3.8,<3.9",
    "GitPython>=3.1,<3.2",
    "pyFirmata>=1.1,<1.2",

    # misc Stytra dependencies
    "anytree>=2.8,<2.9",
    "pims>=0.6,<0.7",
    "colorspacious>=1.1,<1.2",
    "flammkuchen==1.0.3",
    "arrayqueues==1.4.1",
    "lightparam>=0.4,<0.5",
]

TEST_DEPS = [
    "pytest>=7.4,<8.3",
    "pytest-qt>=4.2,<4.5",
]

setup(
    name="stytra",
    version="0.8.35",
    author="Vilim Stih, Luigi Petrucco @portugueslab",
    author_email="vilim@neuro.mpg.de",
    license="GPLv3+",
    packages=find_packages(),
    python_requires=">=3.10,<3.11",

    # Dependencies are managed by environment.yml.
    # This keeps `pip install -e .` from changing the conda environment.
    install_requires=[],

    extras_require={
        "deps": DEPS+TEST_DEPS,
    },

    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Programming Language :: Python :: 3.10",
    ],
    keywords="tracking behavior experiments",
    description="A modular package to control stimulation and track behavior experiments.",
    project_urls={
        "Source": "https://github.com/portugueslab/stytra",
        "Tracker": "https://github.com/portugueslab/stytra/issues",
    },
    include_package_data=True,
)