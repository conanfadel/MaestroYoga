"""FastAPI lifespan hook."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    lvl_name = os.getenv("LOG_LEVEL", "INFO").upper()
    lvl = getattr(logging, lvl_name, logging.INFO)
    logging.getLogger("maestro.request").setLevel(lvl)
    yield
