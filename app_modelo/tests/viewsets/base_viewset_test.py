import json
import time
from unittest.mock import patch

from django.db import connection, models
from django.test import override_settings
from django.urls import reverse, resolve
from model_bakery import baker
from rest_framework import status
from rest_framework.test import APITestCase, APIRequestFactory
from novadata_utils.viewsets import NovadataModelViewSet


class BaseViewsetTest(APITestCase):
    """
    Base class for testing Django ViewSets with standardized tests for CRUD operations,
    pagination, query optimization, and response performance.

    Attributes:
        app (str): The Django app where the model is defined. Must be set in subclasses.
        model (type): The model class being tested. Must be set in subclasses.
        model_name (str): The lowercase name of the model. Must be set in subclasses.
        valid_payload (dict): A dictionary with valid data for creating or updating instances.
        url_name_list (str): The name of the URL for listing objects.
        url_name_detail (str): The name of the URL for accessing a single object.
        max_num_queries (int): Maximum allowed database queries for list views. Default is 5.
        max_response_size (int): Maximum allowed response size in KB. Default is 100KB.
        allowed_methods (list): List of HTTP methods allowed for the endpoints (e.g., ['GET', 'POST']).
        page_size (int): The number of items per page. Default is 10.
    """

    app = None  # Must be set in subclasses
    model = None  # Must be set in subclasses
    model_name = None  # Must be set in subclasses
    valid_payload = {}  # Must be set in subclasses
    url_name_list = None  # Must be set in subclasses
    url_name_detail = None  # Must be set in subclasses
    max_num_queries = 5
    max_response_size = 100  # KB
    allowed_methods = []
    page_size = 10

    def setUp(self):
        """
        Sets up the test environment by:
        - Validating required attributes.
        - Creating a test user and authenticating it.
        - Mocking `get_current_user` if required by the model.
        - Creating a test instance of the model.
        """
        if (
            not self.model
            or not self.valid_payload
            or not self.url_name_list
            or not self.url_name_detail
        ):
            self.skipTest("Required class attributes are not defined.")

        self.user = baker.make("auth.User")
        self.client.force_authenticate(user=self.user)

        self.patcher = patch(
            f"{self.app}.models.{self.model_name}.get_current_user",
            return_value=self.user,
        )
        self.mock_get_current_user = self.patcher.start()

        self.objeto = baker.make(self.model)

    def tearDown(self):
        """Stops the patcher for `get_current_user`."""
        self.patcher.stop()

    # --- CRUD Tests ---

    def test_list_endpoint(self):
        """Tests the list endpoint for appropriate behavior."""
        url = reverse(self.url_name_list)
        response = self.client.get(url)

        if "GET" in self.allowed_methods:
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        else:
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_retrieve_endpoint(self):
        """Tests the retrieve endpoint for accessing a single object."""
        url = reverse(self.url_name_detail, kwargs={"pk": self.objeto.id})
        response = self.client.get(url)

        if "GET" in self.allowed_methods:
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["id"], self.objeto.id)
        else:
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_create_valid_payload(self):
        """Tests object creation with valid payload."""
        url = reverse(self.url_name_list)
        response = self.client.post(url, self.valid_payload)

        if "POST" in self.allowed_methods:
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        else:
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_create_invalid_payload(self):
        """Tests object creation with invalid payload."""
        url = reverse(self.url_name_list)
        invalid_payload = {"invalid_field": "value"}
        response = self.client.post(url, invalid_payload)

        if "POST" in self.allowed_methods:
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        else:
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_update_object(self):
        """Tests object update using a valid payload."""
        url = reverse(self.url_name_detail, kwargs={"pk": self.objeto.id})
        response = self.client.patch(url, self.valid_payload)

        if "PATCH" in self.allowed_methods:
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        else:
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_delete_object(self):
        """Tests object deletion."""
        url = reverse(self.url_name_detail, kwargs={"pk": self.objeto.id})
        response = self.client.delete(url)

        if "DELETE" in self.allowed_methods:
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertFalse(self.model.objects.filter(id=self.objeto.id).exists())
        else:
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
            self.assertTrue(self.model.objects.filter(id=self.objeto.id).exists())

    # --- Authentication Tests ---

    def test_unauthenticated_access(self):
        """Tests that endpoints require authentication."""
        self.client.logout()
        url_list = reverse(self.url_name_list)
        url_detail = reverse(self.url_name_detail, kwargs={"pk": self.objeto.id})

        self.assertEqual(
            self.client.get(url_list).status_code, status.HTTP_401_UNAUTHORIZED
        )
        self.assertEqual(
            self.client.get(url_detail).status_code, status.HTTP_401_UNAUTHORIZED
        )
        self.assertEqual(
            self.client.post(url_list, self.valid_payload).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    # --- Performance Tests ---

    @override_settings(DEBUG=True)
    def test_query_count(self):
        """Validates that the query count for the list endpoint is within acceptable limits."""
        baker.make(self.model, _quantity=10000)
        url = reverse(self.url_name_list)
        connection.queries.clear()
        response = self.client.get(url)
        query_count = len(connection.queries)

        if "GET" in self.allowed_methods:
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertLessEqual(query_count, self.max_num_queries)
        else:
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_response_size(self):
        """Ensures the response size does not exceed the maximum allowed limit."""
        baker.make(self.model, _quantity=self.page_size)
        url = reverse(self.url_name_list)
        response = self.client.get(url)

        if "GET" in self.allowed_methods:
            response_size_kb = len(json.dumps(response.json())) / 1024
            self.assertLessEqual(response_size_kb, self.max_response_size)
        else:
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_execution_time_under_1s(self):
        """Validates that the list endpoint executes in under 1 second for 10k objects."""
        baker.make(self.model, _quantity=10000)
        url = reverse(self.url_name_list)

        start_time = time.time()
        response = self.client.get(url)
        execution_time = time.time() - start_time

        if "GET" in self.allowed_methods:
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertLess(execution_time, 1)
        else:
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # --- Pagination Tests ---

    def test_pagination_page_size(self):
        """Ensures the list endpoint is paginated with the correct page size."""
        baker.make(self.model, _quantity=self.page_size + 5)
        url = reverse(self.url_name_list)
        response = self.client.get(url)

        if "GET" in self.allowed_methods:
            results = response.json().get("results", [])
            self.assertEqual(len(results), self.page_size)
        else:
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_pagination_across_pages(self):
        """Tests pagination navigation across multiple pages."""
        baker.make(self.model, _quantity=2 * self.page_size + 1)
        url = reverse(self.url_name_list)

        page_1 = self.client.get(f"{url}?page=1")
        page_2 = self.client.get(f"{url}?page=2")

        if "GET" in self.allowed_methods:
            self.assertEqual(len(page_1.json()["results"]), self.page_size)
            self.assertEqual(len(page_2.json()["results"]), self.page_size)
            self.assertNotEqual(page_1.json()["results"], page_2.json()["results"])
        else:
            self.assertEqual(
                page_1.response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED
            )
            self.assertEqual(
                page_2.response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED
            )

    def test_search_fields_are_defined(self):
        """
        Tests if the `search_fields` property is defined and not empty in the ViewSet.

        This test ensures:
        - The `search_fields` attribute exists in the resolved ViewSet class.
        - The attribute is a non-empty list or tuple.
        """
        try:
            # Resolve the URL to get the view function
            url = reverse(self.url_name_list)
            resolved_view = resolve(url)
            view_func = resolved_view.func
        except Exception as e:
            self.fail(
                f"Failed to resolve the URL with the name '{self.url_name_list}': {e}"
            )

        # Get the ViewSet class from the `initkwargs` of the view function
        view_class = view_func.initkwargs.get("viewset", None) or getattr(
            view_func, "cls", None
        )
        if not view_class:
            self.skipTest(
                "Could not resolve the ViewSet class from the resolved function."
            )

        # Check if the resolved class is a subclass of NovadataModelViewSet
        if not issubclass(view_class, NovadataModelViewSet):
            self.fail(
                f"The resolved class `{view_class.__name__}` is not a subclass of `NovadataModelViewSet`."
            )

        # Verify that `search_fields` is defined and is not empty
        search_fields = getattr(view_class, "search_fields", None)
        self.assertIsNotNone(
            search_fields,
            f"`search_fields` is not defined in the class `{view_class.__name__}`.",
        )
        self.assertTrue(
            isinstance(search_fields, (list, tuple)) and len(search_fields) > 0,
            f"`search_fields` is either empty or not a list/tuple in the class `{view_class.__name__}`.",
        )

    def test_all_foreign_keys_in_filterset_fields(self):
        """
        Tests if all foreign key fields in the model are included in the `filterset_fields` of the ViewSet.

        This ensures:
        - All `ForeignKey` fields in the model have corresponding entries in the `filterset_fields` property of the ViewSet.
        """
        try:
            # Resolve the URL to get the view function
            url = reverse(self.url_name_list)
            resolved_view = resolve(url)
            view_func = resolved_view.func
        except Exception as e:
            self.fail(
                f"Failed to resolve the URL with the name '{self.url_name_list}': {e}"
            )

        # Get the ViewSet class from the `initkwargs` of the view function
        view_class = view_func.initkwargs.get("viewset", None) or getattr(
            view_func, "cls", None
        )
        if not view_class:
            self.skipTest(
                "Could not resolve the ViewSet class from the resolved function."
            )

        # Check if the resolved class is a subclass of NovadataModelViewSet
        if not issubclass(view_class, NovadataModelViewSet):
            self.fail(
                f"The resolved class `{view_class.__name__}` is not a subclass of `NovadataModelViewSet`."
            )

        # Retrieve the `filterset_fields` property
        filterset_fields = getattr(view_class, "filterset_fields", None)
        if not filterset_fields:
            self.fail(
                f"`filterset_fields` is not defined in the ViewSet `{view_class.__name__}`."
            )

        # Get all foreign key fields from the model
        foreign_keys = [
            field.name
            for field in self.model._meta.get_fields()
            if field.is_relation and field.many_to_one and not field.auto_created
        ]

        # Check if all foreign keys are in the `filterset_fields`
        missing_fields = [fk for fk in foreign_keys if fk not in filterset_fields]
        self.assertFalse(
            missing_fields,
            f"The following foreign key fields are missing in `filterset_fields`: {', '.join(missing_fields)}",
        )

    def test_filterset_fields(self):
        """
        Tests the functionality of filters defined in the `filterset_fields` attribute
        of the ViewSet, handling different field types such as ForeignKey, text, numbers, etc.
        """
        try:
            # Resolve the URL to get the associated ViewSet
            url = reverse(self.url_name_list)
            resolved_view = resolve(url)
            view_func = resolved_view.func
        except Exception as e:
            self.fail(
                f"Failed to resolve the URL with the name '{self.url_name_list}': {e}"
            )

        # Get the ViewSet class
        view_class = view_func.initkwargs.get("viewset", None) or getattr(
            view_func, "cls", None
        )
        if not view_class:
            self.skipTest(
                "Could not resolve the ViewSet class from the resolved function."
            )

        # Ensure the `filterset_fields` attribute is defined in the ViewSet
        filterset_fields = getattr(view_class, "filterset_fields", None)
        if not filterset_fields:
            self.skipTest(
                f"`filterset_fields` is not defined in the ViewSet `{view_class.__name__}`."
            )

        # Exclude fields that should not be tested
        filterset_fields = [
            field
            for field in filterset_fields
            if field not in ["usuario_criacao", "usuario_atualizacao"]
        ]

        # Iterate over the fields in `filterset_fields` and test their functionality
        for field in filterset_fields:
            with self.subTest(filter_field=field):
                # Get the type of the field from the model
                model_field = self.model._meta.get_field(field)

                if model_field.is_relation:  # ForeignKey or ManyToOne fields
                    related_model = model_field.related_model
                    related_obj_1 = baker.make(related_model)
                    related_obj_2 = baker.make(related_model)
                    obj_1 = baker.make(self.model, **{field: related_obj_1})
                    obj_2 = baker.make(self.model, **{field: related_obj_2})
                    filter_value_1 = related_obj_1.pk
                    filter_value_2 = related_obj_2.pk
                else:
                    self.skipTest(f"Field type not supported: {type(model_field)}")

                # Test filtering with the first value
                response = self.client.get(f"{url}?{field}={filter_value_1}")
                self.assertEqual(response.status_code, status.HTTP_200_OK)

                # Verify only the first object is in the results
                results = response.json().get("results", [])
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0]["id"], obj_1.id)

                # Test filtering with the second value
                response = self.client.get(f"{url}?{field}={filter_value_2}")
                self.assertEqual(response.status_code, status.HTTP_200_OK)

                # Verify only the second object is in the results
                results = response.json().get("results", [])
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0]["id"], obj_2.id)
