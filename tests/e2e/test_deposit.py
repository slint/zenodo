# -*- coding: utf-8 -*-
#
# This file is part of Zenodo.
# Copyright (C) 2017 CERN.
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

"""Deposit E2E testing."""

from __future__ import absolute_import, print_function

from flask import url_for
from helpers import login_user
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait


def test_minimum_deposit(live_server, env_browser, license_record, users,
                         text_file_path):
    """Test retrieval of frontpage."""
    login_user(env_browser, 'info@zenodo.org', 'tester')
    env_browser.get(url_for('invenio_deposit_ui.new', _external=True))

    assert 'New upload' in env_browser.page_source

    # Wait for the file upload box to be visible
    wait = WebDriverWait(env_browser, 15)
    file_input = wait.until(EC.visibility_of_element_located(
        (By.CSS_SELECTOR, 'input[type="file"][ngf-select]')))
    file_input.send_keys(text_file_path)
    env_browser.find_element_by_css_selector(
        'invenio-files-list button[type="submit"]').click()

    env_browser.find_element_by_id('title').send_keys('Test title')
    env_browser.find_element_by_css_selector(
        'div[ng-model="model[\'creators\']"] #name').send_keys('Doe, John ')

    # To get the description field, we need to get the CKEditor iframe...
    ckeditor = env_browser.find_element_by_css_selector(
        'div[model="model[\'description\']"] iframe')
    env_browser.switch_to.frame(ckeditor)
    ckeditor_body = env_browser.find_element_by_tag_name('body')
    ckeditor_body.clear()
    ckeditor_body.send_keys('Test description')

    env_browser.switch_to.default_content()

    # select a license
    env_browser.find_element_by_css_selector(
        'div[placeholder="Start typing a license name..."]').click()
