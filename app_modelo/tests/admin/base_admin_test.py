from django.contrib.admin import site
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from model_bakery import baker
from rest_framework import status


class BaseAdminTest(TestCase):
    """
    Base class for testing Django admin classes.

    Attributes:
        admin_class (type): The admin class to be tested. Must be defined in subclasses.
        app (str): The name of the Django app where the model is located. Must be defined in subclasses.
        model (type): The model class to be tested. Must be defined in subclasses.
        model_name (str): The name of the model in lowercase. Must be defined in subclasses.
        valid_payload (dict): A dictionary with valid data for creating or editing a model instance.
    """

    admin_class = None  # Specify the admin class in subclasses
    app = None  # Specify the app name in subclasses
    model = None  # Specify the model in subclasses
    model_name = None  # Specify the model name in subclasses
    valid_payload = None  # Specify valid data payload for the model in subclasses

    def setUp(self):
        """
        Sets up the test environment:
        - Ensures the admin class and model are defined.
        - Creates a superuser and logs them into the admin site.
        """
        # Fetch the registered admin instance for the model
        self.admin_instance = site._registry.get(self.model)
        if not self.admin_class or not self.model:
            self.skipTest("Admin class or model not defined.")

        # Create a superuser for testing
        self.user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="password"
        )
        self.client.login(username="admin", password="password")

    def test_admin_is_registered(self):
        """Validates that the admin class is registered with the Django admin site."""
        self.assertIn(self.model, site._registry)

    def test_list_display(self):
        """Validates the `list_display` attribute in the admin class."""
        self.assertEqual(
            self.admin_instance.list_display, self.admin_class.list_display
        )

    def test_search_fields(self):
        """Validates the `search_fields` attribute in the admin class."""
        self.assertEqual(
            self.admin_instance.search_fields, self.admin_class.search_fields
        )

    def test_autocomplete_fields(self):
        """Validates the `autocomplete_fields` attribute in the admin class."""
        self.assertEqual(
            self.admin_instance.autocomplete_fields,
            self.admin_class.autocomplete_fields,
        )

    def test_readonly_fields(self):
        """Validates the `readonly_fields` attribute in the admin class."""
        self.assertEqual(
            self.admin_instance.readonly_fields, self.admin_class.readonly_fields
        )

    def test_filter_horizontal(self):
        """Validates the `filter_horizontal` attribute in the admin class."""
        self.assertEqual(
            self.admin_instance.filter_horizontal, self.admin_class.filter_horizontal
        )

    def test_fieldsets(self):
        """Validates the `fieldsets` attribute in the admin class."""
        self.assertEqual(self.admin_instance.fieldsets, self.admin_class.fieldsets)

    def test_inlines(self):
        """Validates the `inlines` attribute in the admin class."""
        self.assertEqual(self.admin_instance.inlines, self.admin_class.inlines)

    def test_access_changelist_view(self):
        """Tests access to the changelist view in the admin interface."""
        url = reverse(f"admin:{self.app}_{self.model_name}_changelist")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_access_add_view(self):
        """Tests access to the add form in the admin interface."""
        url = reverse(f"admin:{self.app}_{self.model_name}_add")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_create_object_via_admin(self):
        """Tests creating a new object through the admin interface."""
        url = reverse(f"admin:{self.app}_{self.model_name}_add")
        response = self.client.post(url, self.valid_payload)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertTrue(self.model.objects.count() == 1)

    def test_edit_object_via_admin(self):
        """Tests editing an existing object through the admin interface."""
        obj_instance = baker.make(self.model)
        url = reverse(
            f"admin:{self.app}_{self.model_name}_change", args=[obj_instance.id]
        )
        response = self.client.post(url, self.valid_payload)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)

    def test_delete_object_via_admin(self):
        """Tests deleting an object through the admin interface."""
        obj_instance = baker.make(self.model)
        url = reverse(
            f"admin:{self.app}_{self.model_name}_delete", args=[obj_instance.id]
        )
        response = self.client.post(url, {"post": "yes"})  # Confirm deletion
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertFalse(self.model.objects.filter(id=obj_instance.id).exists())

    def test_all_foreign_keys_in_list_filter_fields(self):
        """
        Tests if all foreign key fields in the model are included in the `list_filter` of the Admin.

        This ensures:
        - All `ForeignKey` fields in the model have corresponding entries in the `list_filter` property of the Admin.
        """
        # Retrieve the `list_filter` property
        list_filter = getattr(self.admin_class, "list_filter", None)

        # Get all foreign key fields from the model
        foreign_keys = [
            field.name
            for field in self.model._meta.get_fields()
            if field.is_relation and field.many_to_one and not field.auto_created
        ]

        # Check if all foreign keys are in the `list_filter`
        missing_fields = [fk for fk in foreign_keys if fk not in list_filter]
        self.assertFalse(
            missing_fields,
            f"The following foreign key fields are missing in `list_filter`: {', '.join(missing_fields)}",
        )

    def test_all_m2m_keys_in_filter_horizontal_fields(self):
        """
        Tests if all m2m key fields in the model are included in the `filter_horizontal` of the Admin.

        This ensures:
        - All `M2M` fields in the model have corresponding entries in the `filter_horizontal` property of the Admin.
        """
        # Retrieve the `filter_horizontal` property
        filter_horizontal = getattr(self.admin_class, "filter_horizontal", None)

        # Get all m2m key fields from the model
        m2m_keys = [
            field.name
            for field in self.model._meta.get_fields()
            if field.is_relation and field.many_to_many and not field.auto_created
        ]

        # Check if all m2m keys are in the `filter_horizontal`
        missing_fields = [fk for fk in m2m_keys if fk not in filter_horizontal]
        self.assertFalse(
            missing_fields,
            f"The following m2m key fields are missing in `filter_horizontal`: {', '.join(missing_fields)}",
        )

    def test_has_search_fields(self):
        """
        Tests if has search fields defined in the Admin.
        """
        # Retrieve the `search_fields` property
        search_fields = getattr(self.admin_class, "search_fields", None)
        if not search_fields:
            self.fail(
                f"`search_fields` is not defined in the Admin `{self.admin_class.__name__}`."
            )

        self.assertGreaterEqual(len(search_fields), 1, "No search fields defined.")

    def test_create_and_update_fields_are_in_readonly_fields(self):
        """Tests if the ModelAdmin has the correct readonly_fields for creation and update fields."""
        expected_fields = [
            "data_criacao",
            "data_atualizacao",
            "usuario_criacao",
            "usuario_atualizacao",
        ]
        readonly_fields = getattr(self.admin_class, "readonly_fields", [])

        # Check if all expected fields are in the `readonly_fields`
        missing_fields = [
            field for field in expected_fields if field not in readonly_fields
        ]
        self.assertFalse(
            missing_fields,
            f"The following expected fields are missing in `readonly_field`: {', '.join(missing_fields)}",
        )
