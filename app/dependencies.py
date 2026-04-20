from app.services.artic_client import ArtInstituteClient


def get_artic_client() -> ArtInstituteClient:
    return ArtInstituteClient()
