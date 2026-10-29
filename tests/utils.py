import datetime, hashlib, json

from polarrouteserver.route_api.models import Mesh

from django.conf import settings
from django.utils import timezone

def add_test_mesh_to_db():
    """utility function to add a mesh to the test db"""
    with open(settings.TEST_MESH_PATH, 'r') as f:
        file_contents = f.read().encode('utf-8')
        md5 = hashlib.md5(file_contents).hexdigest()
        mesh = json.loads(file_contents)
    return Mesh.objects.create(
            valid_date_start = timezone.now().date() - datetime.timedelta(days=3),
            valid_date_end = timezone.now().date(),
            created = datetime.datetime.now(datetime.UTC),
            md5 = md5,
            meshiphi_version = "test",
            lat_min = mesh["config"]["mesh_info"]["region"]["lat_min"],
            lat_max = mesh["config"]["mesh_info"]["region"]["lat_max"],
            lon_min = mesh["config"]["mesh_info"]["region"]["long_min"],
            lon_max = mesh["config"]["mesh_info"]["region"]["long_max"],
            json = mesh
        )