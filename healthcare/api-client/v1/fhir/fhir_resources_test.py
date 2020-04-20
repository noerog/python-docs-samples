# Copyright 2018 Google LLC All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import pytest
import sys
import uuid

from googleapiclient.errors import HttpError
from retrying import retry

# Add datasets for bootstrapping datasets for testing
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "datasets"))  # noqa
import datasets
import fhir_stores
import fhir_resources

cloud_region = "us-central1"
project_id = os.environ["GOOGLE_CLOUD_PROJECT"]
service_account_json = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]

bundle = os.path.join(os.path.dirname(__file__), "resources/execute_bundle.json")
dataset_id = "test_dataset_{}".format(uuid.uuid4())
fhir_store_id = "test_fhir_store-{}".format(uuid.uuid4())
resource_type = "Patient"


def retry_if_server_exception(exception):
    return isinstance(exception, (HttpError))


@pytest.fixture(scope="module")
def test_dataset():
    @retry(
        wait_exponential_multiplier=1000,
        wait_exponential_max=10000,
        stop_max_attempt_number=10,
        retry_on_exception=retry_if_server_exception,
    )
    def create():
        try:
            datasets.create_dataset(project_id, cloud_region, dataset_id)
        except HttpError as err:
            # We ignore 409 conflict here, because we know it's most
            # likely the first request failed on the client side, but
            # the creation suceeded on the server side.
            if err.resp.status == 409:
                print("Got exception {} while creating dataset".format(err.resp.status))
            else:
                raise

    create()

    yield

    # Clean up
    @retry(
        wait_exponential_multiplier=1000,
        wait_exponential_max=10000,
        stop_max_attempt_number=10,
        retry_on_exception=retry_if_server_exception,
    )
    def clean_up():
        try:
            datasets.delete_dataset(project_id, cloud_region, dataset_id)
        except HttpError as err:
            # The API returns 403 when the dataset doesn't exist.
            if err.resp.status == 404 or err.resp.status == 403:
                print("Got exception {} while deleting dataset".format(err.resp.status))
            else:
                raise

    clean_up()


@pytest.fixture(scope="module")
def test_fhir_store():
    @retry(
        wait_exponential_multiplier=1000,
        wait_exponential_max=10000,
        stop_max_attempt_number=10,
        retry_on_exception=retry_if_server_exception,
    )
    def create():
        try:
            fhir_stores.create_fhir_store(
                project_id, cloud_region, dataset_id, fhir_store_id
            )
        except HttpError as err:
            # We ignore 409 conflict here, because we know it's most
            # likely the first request failed on the client side, but
            # the creation suceeded on the server side.
            if err.resp.status == 409:
                print(
                    "Got exception {} while creating FHIR store".format(err.resp.status)
                )
            else:
                raise

    create()

    yield

    # Clean up
    @retry(
        wait_exponential_multiplier=1000,
        wait_exponential_max=10000,
        stop_max_attempt_number=10,
        retry_on_exception=retry_if_server_exception,
    )
    def clean_up():
        try:
            fhir_stores.delete_fhir_store(
                project_id, cloud_region, dataset_id, fhir_store_id
            )
        except HttpError as err:
            # The API returns 403 when the FHIR store doesn't exist.
            if err.resp.status == 404 or err.resp.status == 403:
                print(
                    "Got exception {} while deleting FHIR store".format(err.resp.status)
                )
            else:
                raise

    clean_up()


# Fixture that creates/deletes a Patient resource for various tests.
@pytest.fixture(scope="module")
def test_patient():
    patient_response = fhir_resources.create_patient(
        project_id, cloud_region, dataset_id, fhir_store_id,
    )
    patient_resource_id = patient_response["id"]

    yield patient_resource_id

    @retry(
        wait_exponential_multiplier=1000,
        wait_exponential_max=10000,
        stop_max_attempt_number=10,
        retry_on_exception=retry_if_server_exception,
    )
    # Clean up
    def clean_up():
        try:
            fhir_resources.delete_resource(
                project_id,
                cloud_region,
                dataset_id,
                fhir_store_id,
                resource_type,
                patient_resource_id,
            )

        except HttpError as err:
            # The API returns 200 whether the resource exists or was
            # successfully deleted or not, so only retry on
            # unathorized exceptions.
            if err.resp.status == 401:
                print(
                    "Got exception {} while deleting FHIR store".format(err.resp.status)
                )
            else:
                raise

    clean_up()


def test_create_patient(test_dataset, test_fhir_store, capsys):
    # Manually create a new Patient here to test that creating a Patient
    # works.
    fhir_resources.create_patient(
        project_id, cloud_region, dataset_id, fhir_store_id,
    )

    out, _ = capsys.readouterr()

    print(out)

    assert "Created Patient" in out


def test_get_patient(test_dataset, test_fhir_store, test_patient, capsys):
    fhir_resources.get_resource(
        project_id,
        cloud_region,
        dataset_id,
        fhir_store_id,
        resource_type,
        test_patient,
    )

    out, _ = capsys.readouterr()

    print(out)

    assert "Got Patient resource" in out


def test_update_patient(test_dataset, test_fhir_store, test_patient, capsys):
    fhir_resources.update_resource(
        project_id,
        cloud_region,
        dataset_id,
        fhir_store_id,
        resource_type,
        test_patient,
    )

    out, _ = capsys.readouterr()

    print(out)

    assert "Updated Patient resource" in out


def test_resource_versions(test_dataset, test_fhir_store, test_patient, capsys):
    # We have to update the resource so that different versions of it are
    # created, then we test to see if we can get/delete those versions.
    fhir_resources.update_resource(
        project_id,
        cloud_region,
        dataset_id,
        fhir_store_id,
        resource_type,
        test_patient,
    )

    history = fhir_resources.list_resource_history(
        project_id,
        cloud_region,
        dataset_id,
        fhir_store_id,
        resource_type,
        test_patient,
    )

    fhir_resources.get_resource_history(
        project_id,
        cloud_region,
        dataset_id,
        fhir_store_id,
        resource_type,
        test_patient,
        history["entry"][-1]["resource"]["meta"]["versionId"],
    )

    out, _ = capsys.readouterr()

    print(out)

    # list_resource_history test
    assert "History for Patient resource" in out
    # get_resource_history test
    assert "Got history for Patient resource" in out


def test_search_resources_post(test_dataset, test_fhir_store, test_patient, capsys):
    fhir_resources.search_resources_post(
        project_id, cloud_region, dataset_id, fhir_store_id, resource_type,
    )

    out, _ = capsys.readouterr()

    assert "Using POST request" in out


def test_execute_bundle(test_dataset, test_fhir_store, capsys):
    fhir_resources.execute_bundle(
        project_id, cloud_region, dataset_id, fhir_store_id, bundle,
    )

    out, _ = capsys.readouterr()

    assert "Executed bundle from file" in out


def test_delete_patient(test_dataset, test_fhir_store, test_patient, capsys):
    fhir_resources.delete_resource(
        project_id,
        cloud_region,
        dataset_id,
        fhir_store_id,
        resource_type,
        test_patient,
    )

    out, _ = capsys.readouterr()

    print(out)

    assert "Deleted Patient resource" in out
