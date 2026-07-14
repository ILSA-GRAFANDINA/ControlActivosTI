from django.contrib.auth.hashers import ScryptPasswordHasher


class ControlActivosScryptPasswordHasher(ScryptPasswordHasher):
    """Scrypt ajustado para una validación interactiva segura y ágil."""

    work_factor = 2**16
    block_size = 8
    parallelism = 1
    maxmem = 128 * 1024 * 1024
