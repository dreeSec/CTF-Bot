from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import DefaultDict, List, Set
import sqlite3


@dataclass
class Chall_board_indicies:
    category_name_index: int = -1
    last_challenge_index: int = -1


@dataclass
class Category_and_challenge:
    category: str = ""
    challenge: str = ""


@dataclass
class Challenges:
    chall_board_msg_ids: List[int] = field(default_factory=list)
    chall_board_field_count: int = 0
    category_to_chall_board: DefaultDict[str, Chall_board_indicies] = field(
        default_factory=lambda: defaultdict(Chall_board_indicies))
    category_challenge_to_chall_board: DefaultDict[Category_and_challenge, int] = field(
        default_factory=lambda: defaultdict(int))
    thread_id_to_challenge: DefaultDict[int, Category_and_challenge] = field(
        default_factory=lambda: defaultdict(Category_and_challenge))

    hidden_challs: Set = field(default_factory=set)
    solved_challs: Set = field(default_factory=set)
    solves_per_user: DefaultDict[int, int] = field(
        default_factory=lambda: defaultdict(int))


@dataclass
class Event:
    ctf_verified: bool
    channel_join: int
    channel_logs: int
    channel_challenges: int
    channel_general: int
    join_message: int
    challenges: Challenges


@dataclass
class ServerData:
    events: DefaultDict[int, Event] = field(
        default_factory=lambda: defaultdict(Event))
    event_categories: DefaultDict[int, int] = field(
        default_factory=lambda: defaultdict(int))
    user_to_ctfd: DefaultDict[int, int] = field(
        default_factory=lambda: defaultdict(int))
    archived_events: List[int] = field(default_factory=list)
    # reminders: DefaultDict[int, datetime] = field(
    #     default_factory=lambda: defaultdict(datetime))


@dataclass
class GlobalData:
    servers: DefaultDict[int, ServerData] = field(
        default_factory=lambda: defaultdict(ServerData))

# initialize sqlite database file


def init_db():
    conn = sqlite3.connect('ctfbot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS servers
                 (id INTEGER PRIMARY KEY, data TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS global
                 (id INTEGER PRIMARY KEY, data TEXT)''')
    conn.commit()
    conn.close()
