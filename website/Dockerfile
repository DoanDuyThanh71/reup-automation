FROM python:3.11-slim

WORKDIR /srv/portal

RUN pip install --no-cache-dir fastapi uvicorn[standard] python-multipart pydantic

COPY server.py /srv/portal/server.py
COPY payment_gateway.py /srv/portal/payment_gateway.py
COPY payos.py /srv/portal/payos.py
COPY static /srv/portal/static
COPY taste /srv/portal/taste
COPY demos /srv/portal/demos

ENV PORTAL_PORT=8088
EXPOSE 8088

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8088"]
