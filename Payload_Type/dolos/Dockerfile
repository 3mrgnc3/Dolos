# Dolos v2 service container (Mythic wrapper payload type).
# Pure-Python: mythic_python_base + paramiko (SSH/SFTP).
#
# v2: Flat-file configs at /Mythic/ root — visible in paperclip UI.
# No separate bind mount. SSH keys via Mythic User Secrets.

FROM itsafeaturemythic/mythic_python_base:latest

RUN pip3 install --upgrade mythic_container==0.6.16
RUN pip3 install paramiko

# Copy agent code
COPY main.py /Mythic/main.py
COPY dolos/ /Mythic/dolos/

# Copy v2 flat-file configs to /Mythic/ root — visible in paperclip UI
COPY 00_Encoder_PyEncoder.json /Mythic/
COPY 00_Tool_pyencoder_encode.py /Mythic/
COPY 00_Tool_pyencoder_install.ps1 /Mythic/

WORKDIR /Mythic/

CMD ["python3", "main.py"]