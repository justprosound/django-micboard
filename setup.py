"""
Setup configuration for django-micboard package.
"""
from setuptools import setup, find_packages
import os

# Read the long description from README
with open('README.md', 'r', encoding='utf-8') as f:
    long_description = f.read()

# Read version from micboard/__init__.py
def get_version():
    version_file = os.path.join(os.path.dirname(__file__), 'micboard', '__init__.py')
    with open(version_file, 'r') as f:
        for line in f:
            if line.startswith('__version__'):
                return line.split('=')[1].strip().strip('"').strip("'")
    return '2.2.0'

setup(
    name='django-micboard',
    version=get_version(),
    description='Django app for monitoring Shure wireless microphone systems via System API',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='Your Name',  # TODO: Update with your name
    author_email='your.email@example.com',  # TODO: Update with your email
    url='https://github.com/yourusername/django-micboard',  # TODO: Update with your repo
    project_urls={
        'Bug Reports': 'https://github.com/yourusername/django-micboard/issues',
        'Source': 'https://github.com/yourusername/django-micboard',
        'Documentation': 'https://github.com/yourusername/django-micboard#readme',
    },
    packages=find_packages(exclude=['tests', 'tests.*', 'docs', 'examples']),
    include_package_data=True,
    package_data={
        'micboard': [
            'static/micboard/**/*',
            'templates/micboard/**/*',
            'management/commands/*.py',
        ],
    },
    install_requires=[
        'Django>=4.2,<6.0',
        'channels>=4.0.0',
        'daphne>=4.0.0',
        'requests>=2.31.0',
        'urllib3>=2.0.0',
        'asgiref>=3.7.0',
    ],
    extras_require={
        'redis': [
            'channels-redis>=4.0.0',
            'redis>=5.0.0',
        ],
        'dev': [
            'pytest>=7.0.0',
            'pytest-django>=4.5.0',
            'pytest-asyncio>=0.21.0',
            'black>=23.0.0',
            'flake8>=6.0.0',
            'mypy>=1.0.0',
        ],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Framework :: Django',
        'Framework :: Django :: 4.2',
        'Framework :: Django :: 5.0',
        'Framework :: Django :: 5.1',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
        'Topic :: Multimedia :: Sound/Audio',
        'Topic :: System :: Monitoring',
    ],
    python_requires='>=3.9',
    keywords='django shure wireless microphone monitoring audio websocket',
    license='MIT',
    zip_safe=False,
)
