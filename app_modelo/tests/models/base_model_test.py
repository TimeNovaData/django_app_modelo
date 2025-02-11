from unittest.mock import patch
from django.test import TestCase
from model_bakery import baker


class BaseModelTest(TestCase):
    """
    Base class for testing Django models.

    Attributes:
        app (str): The name of the Django app where the model is located. Must be defined in subclasses.
        model (type): The model class to be tested. Must be defined in subclasses.
        valid_payload (dict): A dictionary with valid data for creating a model instance.
        model_name (str): The name of the model in lowercase. Must be defined in subclasses.
        objeto (object): An instance of the model, created in `setUp()`.
    """

    app = None  # Specify the app name in subclasses
    model = None  # Specify the model in subclasses
    valid_payload = {}  # Specify valid payload for the model in subclasses
    model_name = None  # Specify the model name in subclasses
    objeto = None

    def setUp(self):
        """
        Prepares the test environment:
        - Ensures required attributes are defined.
        - Creates a user for testing and mocks `get_current_user`.
        - Creates a default instance of the model for testing.
        """
        if not self.model:
            self.skipTest("Model class not defined.")
        if not self.valid_payload:
            self.skipTest("Valid payload not defined.")

        # Create a user for testing
        self.user = baker.make("auth.User")

        # Mock `get_current_user` to return the test user
        self.patcher = patch(
            f"{self.app}.models.{self.model_name}.get_current_user",
            return_value=self.user,
        )
        self.mock_get_current_user = self.patcher.start()

        # Create a default test instance of the model
        self.objeto = baker.make(self.model)

    def tearDown(self):
        """Stops any active patchers after tests are executed."""
        self.patcher.stop()

    def test_can_create_instance(self):
        """
        Tests creating an instance of the model with valid data.
        Verifies the instance is saved correctly in the database.
        """
        instance = self.model.objects.create(**self.valid_payload)
        self.assertIsInstance(instance, self.model)
        self.assertTrue(self.model.objects.filter(id=instance.id).exists())

    def test_str_representation(self):
        """
        Tests the string representation of the model instance.
        Ensures that calling `str(instance)` does not raise exceptions.
        """
        instance = baker.make(self.model)
        self.assertTrue(str(instance))

    def test_creation_date(self):
        """
        Tests if the creation date (`data_criacao`) is correctly assigned.
        """
        self.assertIsNotNone(self.objeto.data_criacao)

    def test_update_date(self):
        """
        Tests if the update date (`data_atualizacao`) is updated correctly on save.
        """
        initial_creation_date = self.objeto.data_criacao
        initial_update_date = self.objeto.data_atualizacao

        # Update object with new values and save
        for key, value in self.valid_payload.items():
            setattr(self.objeto, key, value)
        self.objeto.save()

        # Ensure creation date remains the same and update date changes
        self.assertEqual(self.objeto.data_criacao, initial_creation_date)
        self.assertNotEqual(self.objeto.data_atualizacao, initial_update_date)

    def test_creation_user(self):
        """
        Tests if the creation user (`usuario_criacao`) is correctly assigned.
        """
        self.assertEqual(self.objeto.usuario_criacao, self.user)

    def test_update_user(self):
        """
        Tests if the update user (`usuario_atualizacao`) is updated correctly.
        """
        user_update = baker.make("auth.User")

        # Mock `get_current_user` to return the new user
        with patch(
            f"{self.app}.models.{self.model_name}.get_current_user",
            return_value=user_update,
        ):
            # Update object with new values and save
            for key, value in self.valid_payload.items():
                setattr(self.objeto, key, value)
            self.objeto.save()

        # Verify the update user is set correctly
        self.assertEqual(self.objeto.usuario_atualizacao, user_update)
