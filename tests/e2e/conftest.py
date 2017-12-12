# -*- coding: utf-8 -*-
#
# This file is part of Zenodo.
# Copyright (C) 2015 CERN.
#
# Zenodo is free software; you can redistribute it
# and/or modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# Zenodo is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Zenodo; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place, Suite 330, Boston,
# MA 02111-1307, USA.
#
# In applying this license, CERN does not
# waive the privileges and immunities granted to it by virtue of its status
# as an Intergovernmental Organization or submit itself to any jurisdiction.

"""Pytest configuration.

Before running any of the tests you must have initialized the assets using
the ``script scripts/setup-assets.sh``.
"""

from __future__ import absolute_import, print_function

import os
import shutil
import tempfile

from invenio_pidstore.models import PersistentIdentifier
from invenio_records.api import Record
import pytest
from elasticsearch.exceptions import RequestError
from flask_celeryext import create_celery_app
from invenio_access.models import ActionUsers
from invenio_accounts.testutils import create_test_user
from invenio_admin.permissions import action_admin_access
from invenio_db import db as db_
from invenio_deposit.permissions import \
    action_admin_access as deposit_admin_access
from invenio_search import current_search, current_search_client
from selenium import webdriver
from sqlalchemy_utils.functions import create_database, database_exists
from invenio_indexer.api import RecordIndexer

from zenodo.factory import create_app


@pytest.yield_fixture(scope='session')
def instance_path():
    """Default instance path."""
    path = tempfile.mkdtemp()
    yield path
    shutil.rmtree(path)


@pytest.fixture(scope='session')
def env_config(instance_path):
    """Default instance path."""
    os.environ.update(
        INVENIO_INSTANCE_PATH=os.environ.get(
            'INSTANCE_PATH', instance_path),
    )
    return os.environ


@pytest.yield_fixture(scope='session')
def tmp_db_path():
    """Temporary database path."""
    os_path = tempfile.mkstemp(prefix='zenodo_test_', suffix='.db')[1]
    path = 'sqlite:///' + os_path
    yield path
    os.remove(os_path)


@pytest.fixture(scope='session')
def default_config(tmp_db_path):
    """Default configuration."""
    ZENODO_OPENAIRE_SUBTYPES = {
        'openaire_communities': {
            'foo': ['c1', 'c2'],
            'bar': ['c3', ],
        },
        'openaire_types': {
            'software': {
                'foo': [
                    {'id': 'foo:t1', 'name': 'Foo sft type one'},
                    {'id': 'foo:t2', 'name': 'Foo sft type two'},
                ],
                'bar': [
                    {'id': 'bar:t3', 'name': 'Bar sft type three'},
                ]
            },
            'other': {
                'foo': [
                    {'id': 'foo:t4', 'name': 'Foo other type four'},
                    {'id': 'foo:t5', 'name': 'Foo other type five'},
                ],
                'bar': [
                    {'id': 'bar:t6', 'name': 'Bar other type six'},
                ]
            }
        }
    }

    return dict(
        CELERY_ALWAYS_EAGER=True,
        CELERY_EAGER_PROPAGATES_EXCEPTIONS=True,
        CFG_SITE_NAME="testserver",
        COMMUNITIES_MAIL_ENABLED=False,
        DEBUG_TB_ENABLED=False,
        DEPOSIT_DATACITE_MINTING_ENABLED=False,
        LOGIN_DISABLED=False,
        MAIL_SUPPRESS_SEND=True,
        SECRET_KEY="CHANGE_ME",
        SECURITY_PASSWORD_SALT="CHANGE_ME",
        SIPSTORE_ARCHIVER_WRITING_ENABLED=False,
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            'SQLALCHEMY_DATABASE_URI', 'sqlite:///test.db'),
        TESTING=True,
        # WTF_CSRF_ENABLED=False,
        ZENODO_COMMUNITIES_ADD_IF_GRANTS=['grants_comm', ],
        ZENODO_COMMUNITIES_AUTO_ENABLED=False,
        ZENODO_COMMUNITIES_AUTO_REQUEST=['zenodo', ],
        ZENODO_COMMUNITIES_NOTIFY_DISABLED=['zenodo', 'c2'],
        ZENODO_COMMUNITIES_REQUEST_IF_GRANTS=['ecfunded', ],
        ZENODO_OPENAIRE_SUBTYPES=ZENODO_OPENAIRE_SUBTYPES,
    )


@pytest.yield_fixture(scope='session')
def base_app(env_config, default_config):
    """Flask application fixture."""
    app = create_app(**default_config)
    # FIXME: Needs fixing flask_celeryext,
    # which once creates the first celery app, the flask_app that is set
    # is never released from the global state, even if you create a new
    # celery application. We need to unset the "flask_app" manually.
    from celery import current_app as cca
    cca = cca._get_current_object()
    delattr(cca, "flask_app")
    celery_app = create_celery_app(app)
    celery_app.set_current()

    with app.app_context():
        yield app


@pytest.yield_fixture(scope='session')
def es(base_app):
    """Provide elasticsearch access."""
    try:
        list(current_search.create())
    except RequestError:
        list(current_search.delete(ignore=[400, 404]))
        list(current_search.create())
    current_search_client.indices.refresh()
    yield current_search_client
    list(current_search.delete(ignore=[404]))


@pytest.yield_fixture(scope='session')
def db(base_app):
    """Setup database."""
    if not database_exists(str(db_.engine.url)):
        create_database(str(db_.engine.url))
    db_.create_all()
    yield db_
    db_.session.remove()
    db_.drop_all()


@pytest.yield_fixture(scope='session', autouse=True)
def app(base_app, es, db):
    """Application with ES, DB and Celery."""
    yield base_app


def pytest_generate_tests(metafunc):
    """Override pytest's default test collection function.

    For each test in this directory which uses the `env_browser` fixture,
    the given test is called once for each value found in the
    `E2E_WEBDRIVER_BROWSERS` environment variable.
    """
    if 'env_browser' in metafunc.fixturenames:
        browsers = os.environ.get('E2E_WEBDRIVER_BROWSERS',
                                  'Firefox').split()
        metafunc.parametrize('env_browser', browsers, indirect=True)


@pytest.yield_fixture()
def env_browser(request):
    """Fixture for a webdriver instance of the browser."""
    if request.param is None:
        request.param = "Firefox"

    browser_cls = getattr(webdriver, request.param)
    browser_pkg = getattr(webdriver, request.param.lower())
    options = browser_pkg.options.Options()
    options.add_argument('--headless')
    options_arg_name = '{}_options'.format(request.param.lower())
    browser = browser_cls(**{options_arg_name: options})

    yield browser

    # Quit the webdriver instance
    browser.quit()


@pytest.fixture
def users(base_app, db):
    """Create users."""
    user1 = create_test_user(email='info@zenodo.org', password='tester')
    user2 = create_test_user(email='test@zenodo.org', password='tester2')
    user_admin = create_test_user(email='admin@zenodo.org',
                                  password='admin')

    with db.session.begin_nested():
        # set admin permissions
        db.session.add(ActionUsers(action=action_admin_access.value,
                                   user=user_admin))
        db.session.add(ActionUsers(action=deposit_admin_access.value,
                                   user=user_admin))
    db.session.commit()

    return [
        {'email': user1.email, 'id': user1.id},
        {'email': user2.email, 'id': user2.id},
        {'email': user_admin.email, 'id': user_admin.id}
    ]


@pytest.fixture
def text_file_path():
    fp, os_path = tempfile.mkstemp(prefix='test_file_', suffix='.txt')
    fp.write('some text')
    fp.close()
    return os_path


@pytest.fixture
def license_record(base_app, db, es):
    """Create a license record."""
    license = Record.create({
        "$schema": "https://zenodo.org/schemas/licenses/license-v1.0.0.json",
        "domain_content": True,
        "domain_data": True,
        "domain_software": True,
        "family": "",
        "id": "CC-BY-4.0",
        "maintainer": "Creative Commons",
        "od_conformance": "approved",
        "osd_conformance": "not reviewed",
        "status": "active",
        "title": "Creative Commons Attribution International 4.0",
        "url": "https://creativecommons.org/licenses/by/4.0/"
    })
    PersistentIdentifier.create(
        pid_type='od_lic', pid_value=license['id'], object_type='rec',
        object_uuid=license.id, status='R')
    db.session.commit()
    RecordIndexer().index_by_id(str(license.id))
    return license
