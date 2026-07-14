import datetime, hashlib, json, os

from polarrouteserver.route_api.models import EnvironmentMesh, VehicleMesh, Vehicle

from django.conf import settings
from django.utils import timezone

def add_test_environment_mesh_to_db():
    """utility function to add an environment mesh to the test db"""
    fixture_path = os.path.join(os.path.dirname(__file__), 'fixtures', 'test_vessel_mesh.json')
    
    with open(fixture_path, 'r') as f:
        file_contents = f.read().encode('utf-8')
        md5 = hashlib.md5(file_contents).hexdigest()
        
        mesh = json.loads(file_contents)
        
        # Create environment mesh by removing vehicle-specific data
        if 'config' in mesh and 'vessel_info' in mesh['config']:
            del mesh['config']['vessel_info']
        
        # Remove vehicle performance data from cellboxes if present
        for cellbox in mesh.get('cellboxes', []):
            for key in ['speed', 'resistance', 'fuel']:
                if key in cellbox:
                    del cellbox[key]
    
    return EnvironmentMesh.objects.create(
            valid_date_start = timezone.now().date() - datetime.timedelta(days=3),
            valid_date_end = timezone.now().date(),
            created = datetime.datetime.now(datetime.timezone.utc),
            md5 = md5,
            meshiphi_version = "test",
            name="Test Mesh",
            lat_min = mesh["config"]["mesh_info"]["region"]["lat_min"],
            lat_max = mesh["config"]["mesh_info"]["region"]["lat_max"],
            lon_min = mesh["config"]["mesh_info"]["region"]["long_min"],
            lon_max = mesh["config"]["mesh_info"]["region"]["long_max"],
            json = mesh
        )

def create_test_vehicle():
    """utility function to create a test vehicle"""
    vehicle, created = Vehicle.objects.get_or_create(
        vessel_type="TEST_VESSEL",
        defaults={
            "max_speed": 25.0,
            "unit": "km/hr",
            "max_ice_conc": 80.0,
            "min_depth": 10.0,
            "beam": 20.0,
            "hull_type": "slender",
            "force_limit": 90000.0
        }
    )
    return vehicle

def add_test_vehicle_mesh_to_db():
    """utility function to add a vehicle mesh to the test db"""
    environment_mesh = add_test_environment_mesh_to_db()
    vehicle = create_test_vehicle()
    
    vehicle_fixture_path = os.path.join(os.path.dirname(__file__), 'fixtures', 'test_vessel_mesh.json')
    with open(vehicle_fixture_path, 'r') as f:
        vehicle_mesh_data = json.load(f)
    
    # Use get_or_create to avoid duplicate mesh issues
    vehicle_mesh, created = VehicleMesh.objects.get_or_create(
        environment_mesh=environment_mesh,
        vehicle=vehicle,
        defaults={
            "valid_date_start": environment_mesh.valid_date_start,
            "valid_date_end": environment_mesh.valid_date_end,
            "created": environment_mesh.created,
            "md5": environment_mesh.md5 + "_vehicle",
            "meshiphi_version": environment_mesh.meshiphi_version,
            "lat_min": environment_mesh.lat_min,
            "lat_max": environment_mesh.lat_max,
            "lon_min": environment_mesh.lon_min,
            "lon_max": environment_mesh.lon_max,
            "name": f"{environment_mesh.name} Vehicle",
            "json": vehicle_mesh_data  # Use proper vehicle mesh JSON with vessel_info
        }
    )
    
    return vehicle_mesh