# Single Dolos service container (3rd-Party Service agent).
# Pure-Python: mythic_python_base ships mythic_container; we only add paramiko (SSH/SFTP).
# No COPY — mythic-cli bind-mounts the code into /Mythic/.
FROM itsafeaturemythic/mythic_python_base:latest

RUN pip3 install paramiko

WORKDIR /Mythic/

CMD ["python3", "main.py"]
