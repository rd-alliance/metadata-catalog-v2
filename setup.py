from setuptools import find_packages, setup

setup(
    name='rdamsc',
    version='2.1.0',
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    python_requires='>= 3.8',
    install_requires=[
        'authlib',
        'dulwich',
        'email_validator',
        'flask',
        'flask-cors',
        'flask-httpauth',
        'flask-login',
        'Flask-OpenID',
        'Flask-WTF',
        'github-webhook',
        'oauth2client',
        'passlib',
        'rauth',
        'rdflib',
        'tinydb>=4',
        'tinyrecord>=0.2.0',
    ],
    extras_require={
        'dev': [
            'coverage',
            'pytest',
        ],
    },
)
