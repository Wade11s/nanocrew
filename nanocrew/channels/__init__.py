"""Chat channels module with plugin architecture."""

from nanocrew.channels.base import BaseChannel
from nanocrew.channels.manager import ChannelManager

__all__ = ["BaseChannel", "ChannelManager"]
