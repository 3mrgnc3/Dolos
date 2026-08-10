# Dolos v2 service container (Mythic wrapper payload type).
# Pure-Python: mythic_python_base + paramiko (SSH/SFTP).
#
# v2: Flat-file config in /Mythic/configs/ (paperclip-editable).
# No separate bind mount — configs are baked into the image and editable
# via the Mythic paperclip UI. SSH keys resolved via Mythic User Secrets.

FROM itsafeaturemythic/mythic_python_base:latest

RUN pip3 install --upgrade mythic_container==0.6.16
RUN pip3 install paramiko

# Copy agent code
COPY main.py /Mythic/main.py
COPY dolos/ /Mythic/dolos/

# Copy default v2 configs into /Mythic/configs/ — paperclip-editable
COPY configs/ /Mythic/configs/

WORKDIR /Mythic/

CMD ["python3", "main.py"]