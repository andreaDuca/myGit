from setuptools import setup

setup(
    name='miGyt-version-controll',
    version='0.1',
    py_modules=['libmyGit'],
    entry_points={
        'console_scripts': [
            'myGit = libmyGit:main',
        ],
    },
)