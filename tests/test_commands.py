import json
from io import StringIO
from unittest.mock import patch, MagicMock, mock_open

from django.test import TestCase
from django.core.management import call_command
from django.core.management.base import CommandError

from polarrouteserver.route_api.management.commands.insert_mesh import Command
from polarrouteserver.route_api.models import Vehicle


class TestLoadVehicleFixturesCommand(TestCase):

    def test_adds_default_vehicles(self):
        call_command("load_vehicle_fixtures", stdout=StringIO())

        vehicles = Vehicle.objects.in_bulk()
        assert set(vehicles) == {"SDA", "Slocum", "BoatyMcBoatFace"}
        assert all(v.created_by == "fixture" for v in vehicles.values())

    def test_existing_vehicles_are_not_changed(self):
        Vehicle.objects.create(vessel_type="SDA", max_speed=99.0, unit="km/hr", created_by="user")

        call_command("load_vehicle_fixtures", stdout=StringIO())

        sda = Vehicle.objects.get(vessel_type="SDA")
        assert (sda.max_speed, sda.created_by) == (99.0, "user")
        assert Vehicle.objects.count() == 3

    def test_can_be_run_again(self):
        call_command("load_vehicle_fixtures", stdout=StringIO())
        Vehicle.objects.filter(vessel_type="Slocum").update(max_speed=2.0)

        call_command("load_vehicle_fixtures", stdout=StringIO())

        assert Vehicle.objects.get(vessel_type="Slocum").max_speed == 2.0
        assert Vehicle.objects.count() == 3


class TestInsertMeshCommand(TestCase):
    """Test case for the insert_mesh management command."""

    def setUp(self):
        self.command = Command()
        self.test_mesh_data = {
            "config": {"mesh_info": {"region": {}}},
            "data": []
        }

    @patch('polarrouteserver.route_api.management.commands.insert_mesh.ingest_mesh')
    @patch('builtins.open', new_callable=mock_open)
    @patch('polarrouteserver.route_api.management.commands.insert_mesh.json.load')
    def test_handle_json_file_success(self, mock_json_load, mock_file_open, mock_ingest):
        """Test successful handling of a JSON mesh file."""
        mock_json_load.return_value = self.test_mesh_data
        mock_mesh = MagicMock(name="test_mesh", md5="test_md5")
        mock_ingest.return_value = (mock_mesh, True, "EnvironmentMesh")
        
        out = StringIO()
        call_command('insert_mesh', '/fake/path/test_mesh.json', stdout=out)
        
        mock_file_open.assert_called_once_with('/fake/path/test_mesh.json', 'r')
        mock_json_load.assert_called_once()
        mock_ingest.assert_called_once()
        
        output = out.getvalue()
        self.assertIn("EnvironmentMesh inserted", output)

    @patch('polarrouteserver.route_api.management.commands.insert_mesh.ingest_mesh')
    @patch('gzip.open', new_callable=mock_open)
    @patch('polarrouteserver.route_api.management.commands.insert_mesh.json.load')
    def test_handle_gzip_file_success(self, mock_json_load, mock_gzip_open, mock_ingest):
        """Test successful handling of a gzipped JSON mesh file."""
        mock_json_load.return_value = self.test_mesh_data
        mock_mesh = MagicMock(name="test_mesh", md5="test_md5")
        mock_ingest.return_value = (mock_mesh, True, "EnvironmentMesh")
        
        call_command('insert_mesh', '/fake/path/test_mesh.json.gz')
        
        mock_gzip_open.assert_called_once()
        mock_json_load.assert_called_once()
        mock_ingest.assert_called_once()

    @patch('polarrouteserver.route_api.management.commands.insert_mesh.ingest_mesh')
    @patch('builtins.open', new_callable=mock_open)
    @patch('polarrouteserver.route_api.management.commands.insert_mesh.json.load')
    def test_handle_existing_mesh(self, mock_json_load, mock_file_open, mock_ingest):
        """Test handling when mesh already exists in database."""
        mock_json_load.return_value = self.test_mesh_data
        mock_mesh = MagicMock(md5="existing_md5")
        mock_ingest.return_value = (mock_mesh, False, "EnvironmentMesh")
        
        out = StringIO()
        call_command('insert_mesh', '/fake/path/existing_mesh.json', stdout=out)
        
        output = out.getvalue()
        self.assertIn("already in database", output)

    @patch('polarrouteserver.route_api.management.commands.insert_mesh.ingest_mesh')
    @patch('builtins.open', new_callable=mock_open)
    @patch('polarrouteserver.route_api.management.commands.insert_mesh.json.load')
    def test_handle_value_error(self, mock_json_load, _mock_file_open, mock_ingest):
        """Test handling of ValueError from ingest_mesh."""
        mock_json_load.return_value = self.test_mesh_data
        mock_ingest.side_effect = ValueError("Invalid mesh format")
        
        with self.assertRaises(CommandError) as cm:
            call_command('insert_mesh', '/fake/path/invalid_mesh.json')
        
        self.assertEqual(str(cm.exception), "Invalid mesh format")

    @patch('builtins.open', new_callable=mock_open)
    @patch('polarrouteserver.route_api.management.commands.insert_mesh.json.load')
    def test_handle_invalid_json_file(self, mock_json_load, _mock_file_open):
        """Test handling of invalid JSON files."""
        mock_json_load.side_effect = json.JSONDecodeError("Invalid JSON", "doc", 0)
        
        with self.assertRaises(json.JSONDecodeError):
            call_command('insert_mesh', '/fake/path/invalid.json')

    def test_handle_nonexistent_file(self):
        """Test handling of non-existent files."""
        with self.assertRaises(FileNotFoundError):
            call_command('insert_mesh', '/nonexistent/file.json')

    def test_add_arguments(self):
        """Test that the command accepts mesh file arguments."""
        parser = MagicMock()
        self.command.add_arguments(parser)
        parser.add_argument.assert_called_once_with("meshes", nargs="+", type=str)

    def test_help_text(self):
        """Test that the command has appropriate help text."""
        self.assertIn("Manually insert a Mesh", self.command.help)

    def test_command_style_output(self):
        """Test that command uses proper Django styling for output."""
        self.assertTrue(hasattr(self.command, 'style'))
