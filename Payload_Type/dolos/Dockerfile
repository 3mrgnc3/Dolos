# Dolos service container (Mythic wrapper payload type).
# Pure-Python: mythic_python_base ships mythic_container; we add paramiko (SSH/SFTP).
#
# Agent code and sample configs are COPY'd into /Mythic/ so the image is
# self-contained. When mythic-cli uses remote_images (no build context / bind mount),
# the container has everything it needs to start.
#
# At runtime, if /Mythic/configs/ is an empty volume mount (first install),
# main.py calls scaffold_if_needed() which creates sample profiles from
# /Mythic/configs.defaults/ templates.

FROM itsafeaturemythic/mythic_python_base:latest

# Pin mythic_container to match our development environment.
# mythic_python_base ships 0.6.0; we need 0.6.16 for consistency.
RUN pip3 install --upgrade mythic_container==0.6.16
RUN pip3 install paramiko

# Copy agent code into the image
COPY main.py /Mythic/main.py
COPY dolos/ /Mythic/dolos/

# Copy sample configs as defaults — these are used by scaffold_if_needed()
# to populate /Mythic/configs/ on first run when the volume is empty.
# The live /Mythic/configs/ directory is overridden by the dolos_profiles
# volume mount, so these defaults only serve as the template source.
COPY configs/ /Mythic/configs.defaults/

WORKDIR /Mythic/

CMD ["python3", "main.py"]