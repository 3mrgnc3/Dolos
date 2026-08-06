# Single Dolos service container (3rd-Party Service agent).
# Pure-Python: mythic_python_base ships mythic_container; we only add paramiko (SSH/SFTP).
# No COPY - mythic-cli bind-mounts the code into /Mythic/.
FROM itsafeaturemythic/mythic_python_base:latest

# Pin mythic_container to match our development environment.
# mythic_python_base ships 0.6.0; we need 0.6.16 for consistency.
RUN pip3 install --upgrade mythic_container==0.6.16
RUN pip3 install paramiko

WORKDIR /Mythic/

CMD ["python3", "main.py"]
