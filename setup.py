from setuptools import find_packages, setup

setup(
    name='rdamsc',
    version='2.0.0',
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    python_requires='>= 3.6',
    install_requires=[
        'flask',
        'Flask-WTF',
        'email_validator',
        'flask-login',
        'Flask-OpenID',
        'rauth',
        'oauth2client',
        'flask-httpauth',
        'passlib',
        'tinydb<4',
        'tinyrecord',
        'rdflib',
        'dulwich',
        'flask-cors',
        'pytest',
        'coverage',
    ],
)
