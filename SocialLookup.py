# SocialLookup.py
# PYTHON_ARGCOMPLETE_OK
from __future__ import annotations

import sys

# --- Fast-path for PowerShell tab-completion ---
# This must run before any heavy imports (polars, pydantic, thefuzz, colorama, argcomplete)
# since process-startup latency directly affects Tab-press responsiveness.
if "--_complete-names" in sys.argv:
	import csv
	import json
	import os
	from pathlib import Path

	_here = Path(__file__).resolve().parent
	_config_path = _here / "sociallookup_config.json"
	_db_path = _here / "socials.csv"  # default, matches AppSettings default

	if _config_path.exists():
		try:
			with open(_config_path, "r") as f:
				_cfg = json.load(f)
				if "database_path" in _cfg:
					_db_path = Path(_cfg["database_path"])
		except (json.JSONDecodeError, OSError):
			pass  # fall back to default path

	try:
		with open(_db_path, "r", newline="", encoding="utf-8") as f:
			reader = csv.DictReader(f)
			for row in reader:
				name = row.get("Name")
				if name:
					print(name)
	except (FileNotFoundError, OSError):
		pass  # No database yet — just return nothing to complete

	sys.exit(0)
# --- End fast-path ---

from datetime import datetime
import json
import os, sys, argparse, hashlib
from urllib.parse import urlparse
from pathlib import Path
from typing import Tuple, Type, Any, NamedTuple
from thefuzz import process, fuzz
import sqlite3 as sql
from colorama import Fore, init
from pydantic import Field
import argcomplete
from argcomplete.completers import ChoicesCompleter
from pydantic_settings import (
	BaseSettings,
	PydanticBaseSettingsSource,
	SettingsConfigDict,
	JsonConfigSettingsSource
)

# TODO: implement a backup?
# TODO: Create an interactive version of "add" when only the -a is supplied.


CONFIG_PATH = Path(__file__).resolve().parent / "sociallookup_config.json"  # By default, look next to this py file.


class Record(NamedTuple):
	ID: str
	Time: datetime
	Name: str
	Twitter: str | None = None
	BlueSky: str | None = None
	Facebook: str | None = None
	Website: str | None = None
	Instagram: str | None = None
	Description: str | None = None

	@classmethod
	def from_row(cls, row: sql.Row) -> "Record":
		data = {k: row[k] for k in row.keys()}
		data["Time"] = datetime.fromisoformat(data["Time"])
		return cls(**data)


class Records:
	"""Handles the reading and writing of a .csv database of social media records."""

	conn: sql.Connection
	cur = sql.Cursor

	config: AppSettings

	def __init__(self, settings: AppSettings):
		self.config = settings

	def __enter__(self) -> 'Records':
		self.load()
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.save()

	def __str__(self):
		return self.get_records_string(self.get_all())

	def load(self):

		if Path(self.config.database_path).exists():

			self.conn = sql.connect(self.config.database_path)
			self.conn.row_factory = sql.Row
			self.cur = self.conn.cursor()

		else:
			raise FileNotFoundError(f"{self.config.database_path}", self.config.database_path)

	def save(self):
		"""Saves both the database and config file."""
		self.config.save()
		self.conn.commit()
		self.conn.close()

	def get_records_string(self, records: Record | list[Record]) -> str:
		"""
		Returns one or more records in an easily readable form, intended for CLI output.
		:param records: A single Record, or a list of Records, to format.
		"""
		if isinstance(records, Record):
			records = [records]

		return "\n".join(self._format_record(r) for r in records)

	def _format_record(self, record: Record) -> str:
		"""Formats a single Record. Internal helper for get_records_string."""
		from colorama import Fore, init
		init(autoreset=True)

		out = Fore.GREEN + f"{record.Name}: " + Fore.RESET + f"[{record.ID}]\n"

		for platform in self.config.platform_names:
			handle = getattr(record, platform, None)
			if handle is not None:
				url = None
				display = handle

				if platform == "Website":
					parts = urlparse(handle)
					display = f"{parts.netloc}{parts.path}"
					url = handle
				else:
					url = get_url(platform, handle)

				if url and "WT_SESSION" in os.environ:
					out += Fore.CYAN + f"\t{platform}: " + Fore.RESET + f"{format_link(display, url)}"
				else:
					out += Fore.CYAN + f"\t{platform}: " + Fore.RESET + f"{display}\n"

		out += f"\tUpdated {record.Time.strftime('%a %b %d, %Y (%H:%M:%S)')}\n"
		return out

	def get_platform_names(self) -> list[str]:
		return self.config.platform_names.copy()

	def update_setting(self, key: str, value: Any):
		"""
		Updates a setting, validates it, and saves the config file.
		:param key: The key of the setting
		:param value: The value of the setting
		"""
		current_data = self.config.model_dump()

		if key not in current_data:
			raise KeyError(f"'{key}' is not a valid setting.")

		current_data[key] = value
		self.config = AppSettings(**current_data)

		with open("config.json", "w") as f:
			f.write(self.config.model_dump_json(indent=4))

		self.config.save()

	def get_all(self) -> list[Record]:
		"""Returns list[Record] containing ALL records from the database."""
		self.cur.execute("SELECT * FROM sociallookup")
		return [Record.from_row(row) for row in self.cur.fetchall()]

	def get_all_names(self) -> list[Record]:
		cur = self.conn.execute("SELECT * FROM socials")
		return cur.fetchall()

	def add(self, record: Record) -> str:
		"""
		Updates a record with modified social handles, or creates a new record
		if a record for this ID doesn't exist yet.
		:param record: The Record to add or update. record.ID is generated from record.Name
						if not already set correctly by the caller.
		:returns: the ID of the added/modified record.
		"""
		hash_id = Records.generate_id(record.Name)
		now = datetime.now()

		record = record._replace(ID=hash_id, Time=now)

		cur = self.conn.execute("SELECT 1 FROM socials WHERE ID = ?", (hash_id,))
		exists = cur.fetchone() is not None

		if exists:
			self.conn.execute("""
	            UPDATE socials
	            SET Time = ?, Name = ?, Twitter = ?, BlueSky = ?, Facebook = ?,
	                Website = ?, Instagram = ?, Description = ?
	            WHERE ID = ?
	        """, (
				record.Time.isoformat(), record.Name, record.Twitter, record.BlueSky,
				record.Facebook, record.Website, record.Instagram, record.Description,
				hash_id
			))
		else:
			self.conn.execute("""
	            INSERT INTO socials (ID, Time, Name, Twitter, BlueSky, Facebook, Website, Instagram, Description)
	            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
	        """, (
				hash_id, record.Time.isoformat(), record.Name, record.Twitter, record.BlueSky,
				record.Facebook, record.Website, record.Instagram, record.Description
			))

		return hash_id

	def rollback(self):
		"""Rolls back the changes to the database."""
		self.conn.rollback()

	def remove(self, name: str, platforms: list) -> Record:
		"""
		Removes the handle for a particular platform from a record.
		:param name: The name of the record to remove the platform handles from.
		:param platforms: The list of platforms to remove.
		:returns: The updated record.
		:raises KeyError: if 'name' doesn't exist.
		"""
		hash_id = Records.generate_id(name)

		cur = self.conn.execute("SELECT * FROM socials WHERE ID = ?", (hash_id,))
		row = cur.fetchone()
		if row is None:
			raise KeyError(f"'{name}' not found in database.")

		for platform in platforms:
			if platform in self.config.platform_names:
				# Column names can't be parameterized with '?' in sqlite3 -- only values can.
				# This is safe here because 'platform' is checked against the known-good
				# self.config.platform_names allowlist above, not raw user input passed straight through.
				self.conn.execute(
					f"UPDATE socials SET {platform} = NULL WHERE ID = ?",
					(hash_id,)
				)

		cur = self.conn.execute("SELECT * FROM socials WHERE ID = ?", (hash_id,))
		return Record.from_row(cur.fetchone())

	def delete(self, name: str) -> Record:
		"""
		Remove a record from the database based on name.
		:param name: The name of the record to remove.
		:returns: A copy of the removed record.
		:raises KeyError: if 'name' doesn't exist.
		"""
		cur = self.conn.execute("SELECT * FROM socials WHERE NAME = ?", (name,))
		rows = cur.fetchone()

		if len(rows) == 0:
			raise KeyError(f"'{name}' not found in database.")
		elif len(rows) > 1:
			raise KeyError(f"'{name}' returned too many records ({len(rows)}).")

		record = Record.from_row(rows[0])

		self.conn.execute("DELETE FROM socials WHERE ID = ?", (name,))

		return record

	def drop(self, hash_id: str) -> Record:
		"""
		Remove a record from the database based on a hash ID.
		:param hash_id: The name of the record to remove.
		:returns: A copy of the removed record.
		:raises KeyError: if 'name' doesn't exist.
		"""
		cur = self.conn.execute("SELECT * FROM socials WHERE ID = ?", (hash_id,))
		rows = cur.fetchall()

		if len(rows) == 0:
			raise KeyError(f"'{hash_id}' not found in database.")
		elif len(rows) > 1:
			raise KeyError(f"'{hash_id}' returned too many records ({len(rows)}).")

		record = Record.from_row(rows[0])

		self.conn.execute("DELETE FROM socials WHERE ID = ?", (hash_id,))

		return record

	def get_by_name(self, name: str) -> Record:
		"""
		Returns a record from the database based on a name. 'name' must be an exact
		match in the database. (case-insensitive).
		:param name: Name of the record to return.
		:return: DataFrame containing the record from the database.
		:raises KeyError: if 'name' doesn't exist in the database, or if the database is corrupt and
		multiple records match the name.
		"""
		cur = self.conn.execute("SELECT 1 FROM socials WHERE NAME = ?", (name,))
		row = cur.fetchone()

		if row is None:
			raise KeyError(f"'{name}' not found in database.")
		return Record.from_row(row)


	def get_id(self, name: str) -> str:
		"""
		Returns the hash ID of a record from the database based on a name.
		:param name: Name of the record to look up.
		:returns: Hash ID of the record from the database.
		:raises KeyError: if 'name' doesn't exist in the database, or if the database is corrupt and
		multiple records match the name.
		"""

		cur = self.conn.execute("SELECT * FROM socials WHERE NAME = ?", (name,))
		row = cur.fetchone()

		if row is None:
			raise KeyError(f"'{name}' not found in database.")
		return Record.from_row(row).ID


	def search_single(self, name: str) -> Record:
		"""
		Performs a fuzzy search of the database's 'name' column and returns the BEST match.
		:param name: Name of the record to look up.
		:returns: Record matching the name
		"""
		records = self.search(name)
		return records[0] if records else None

	def search(self, name: str, cutoff: int = None) -> list[Record]:
		"""
		Performs a fuzzy search of the database's 'name' column and returns ALL matches with
		similarities greater than 'cutoff'.
		:param name: Name of the record to look up.
		:param cutoff: Number between 0 and 100 describing a similarity tolerance. 0 is dissimilar and 100 is exact.
		:return: DataFrame containing the records from the database.
		"""
		if not cutoff: cutoff = self.config.score_cutoff

		cur = self.conn.execute("SELECT Name FROM socials")
		choices = [row["Name"] for row in cur.fetchall()]

		results = process.extractBests(name, choices, scorer=fuzz.token_set_ratio, score_cutoff=cutoff)
		matched_names = [r[0] for r in results]

		if not matched_names:
			return []

		placeholders = ", ".join("?" for _ in matched_names)
		cur = self.conn.execute(
			f"SELECT * FROM socials WHERE Name IN ({placeholders})",
			matched_names
		)
		records = [Record.from_row(row) for row in cur.fetchall()]
		return records

	def get_by_id(self, id_hash: str) -> Record:
		"""Returns a record from the database based on a hash ID.
		:param id_hash: The hash ID of the record to look up.
		:returns: The Record matching the given hash ID.
		:raises KeyError: if 'id_hash' doesn't exist in the database.
		"""
		cur = self.conn.execute("SELECT * FROM socials WHERE ID = ?", (id_hash,))
		row = cur.fetchone()

		if row is None:
			raise KeyError(f"'{id_hash}' not found in database.")
		return Record.from_row(row)

	@staticmethod
	def generate_id(name: str) -> str:
		"""Generate an md5 hash from a string. Used for creating IDs from names."""
		return hashlib.md5(name.lower().encode()).hexdigest()[:8].lower()


class ArgHandler:
	"""Manages command line parameters and redirects code execution to the corresponding blocks."""

	class HandleAddAction(argparse.Action):
		def __call__(self, parser, namespace, values, option_string=None):
			# Store the list of platform pairs (e.g. ["Twitter:@steve"])
			setattr(namespace, self.dest, values)
			# Inject the handler
			setattr(namespace, "handler", ArgHandler.handle_add)

	class HandleRemoveAction(argparse.Action):
		def __call__(self, parser, namespace, values, option_string=None):
			# This stores the list of fields (the 'values')
			setattr(namespace, self.dest, values)
			# This "injects" the handler function into the namespace
			setattr(namespace, "handler", ArgHandler.handle_remove)

	class HandleIDAction(argparse.Action):
		def __call__(self, parser, namespace, values, option_string=None):
			# Store the ID value (taking the first item from the list)
			setattr(namespace, self.dest, values[0])
			# Inject the handler function
			setattr(namespace, "handler", ArgHandler.handle_id)

	@staticmethod
	def get_args(db: Records):
		"""Parses command line arguments."""
		parser = argparse.ArgumentParser(description=f"Social Media Lookup Utility. Retrieves and modifies "
													 f"social media information.")


		defarg = parser.add_argument("name", type=str, nargs="*", default=None,
							help=f"Name of person to look up. If used without another flag, perform a fuzzy search "
								 f"and displays all social media handles for matching persons. "
								 f"If no name is provided, prints the entire database.")


		defarg.completer = ChoicesCompleter(db.get_all_names())

		group = parser.add_mutually_exclusive_group(required=False)

		group.add_argument("-a", "--add", nargs="+", action=ArgHandler.HandleAddAction,
						   help="Add or update a social record (e.g. \"Twitter=@handle Bluesky=@handle\"). "
								"Requires that the Name parameter be an exact match.")
		group.add_argument("-r", "--remove", type=str, nargs='+', action=ArgHandler.HandleRemoveAction,
						   help="Delete social record. Requires that the Name parameter be an exact match.")
		group.add_argument("-d", "--drop", default=False, action="store_const",
						   const=ArgHandler.handle_drop, dest="handler",
						   help="Delete an entire entry. Requires that the Name parameter be an exact match.")
		group.add_argument("-c", "--cutoff", type=int, default=70,
						   help="Search cutoff for fuzzy searching (0 - 100). Lower is less strict. Default is 70.")

		group.add_argument("--_complete-names", action="store_true", dest="complete_names",
						   help=argparse.SUPPRESS)  # Hidden: used by PowerShell completer

		parser.set_defaults(handler=ArgHandler.handle_default)

		argcomplete.autocomplete(parser)
		args = parser.parse_args()

		if getattr(args, "complete_names", False):
			for name in db.get_all_names():
				print(name)
			sys.exit(0)

		if isinstance(args.name, list):  # Make it so the name parameter doesn't need to be in quotation marks
			args.name = " ".join(args.name)

		return args

	@staticmethod
	def handle_add(db, args):
		"""Handles adding or updating a social record with new handles."""
		if not args.name:
			raise ValueError("Name must be provided.")
		else:
			socials = {}
			for item in args.add:
				entry = pair(item)
				platform, handle = entry[0], entry[1]

				# Normalize against known platform names so casing doesn't matter
				# (e.g. "twitter:@x" should still match the "Twitter" field).
				matched = next(
					(p for p in db.config.platform_names if p.lower() == platform.lower()),
					None
				)
				if matched is None:
					raise ValueError(f"'{platform}' is not a recognized platform.")

				socials[matched] = handle

			record = Record(
				ID="",
				Time=datetime.now(),
				Name=args.name,
				**socials
			)

			hash_id = db.add(record)
			print(db.get_records_string(db.get_by_id(hash_id)))


	@staticmethod
	def handle_drop(db, args):
		"""Handles removing a record from the database entirely."""
		if not args.name:
			raise ValueError("Name must be provided.")
		else:
			hash_id = db.get_id(args.name)
			db.drop(db.get_id(args.name))
			print("Removed " + Fore.GREEN + f"{args.name}" + Fore.RESET + f"[{hash_id}].")


	@staticmethod
	def handle_remove(db, args):
		"""Handles removing a social handle from a record."""
		if not args.name:
			raise ValueError("Name must be provided.")
		if not args.remove:
			raise ValueError("Removal requires platform names.")

		valid_platforms = {platform for platform in args.remove}.intersection(db.config.platform_names)

		if not valid_platforms:
			raise ValueError("Platform names not recognized.")
		else:
			record = db.remove(args.name, valid_platforms)
			print("Updated Record:")
			print(db.get_records_string(record))


	@staticmethod
	def handle_default(db: Records, args):
		"""Handles the default program behavior. Fuzzy search for a name or list everything."""
		if not args.name:
			out = db.get_records_string(db.get_all())
			print(out)
		else:
			found = db.search(args.name)
			if len(found) > 0:
				print(db.get_records_string(db.search(args.name)))
			else:
				print("Error: No records found.")


class AppSettings(BaseSettings):
	"""Manages reading and writing of a json file containing default settings."""

	# These are default settings if a .json can't be found.
	database_path: Path = Field(default=Path(__file__).resolve().parent / "socials.csv")
	score_cutoff: int = Field(default=70, ge=0, le=100)  # ge=0 means "greater than or equal to 0"
	platform_names: list[str] = ["Twitter", "BlueSky", "Facebook", "Website", "Instagram", "Description"]
	model_config = SettingsConfigDict(json_file=CONFIG_PATH)

	@classmethod
	def settings_customise_sources(
			cls,
			settings_cls: Type[BaseSettings],
			init_settings: PydanticBaseSettingsSource,
			env_settings: PydanticBaseSettingsSource,
			dotenv_settings: PydanticBaseSettingsSource,
			file_secret_settings: PydanticBaseSettingsSource,
	) -> Tuple[PydanticBaseSettingsSource, ...]:
		return (
			init_settings,
			env_settings,
			JsonConfigSettingsSource(settings_cls),
		)

	def save(self):
		config_path = CONFIG_PATH

		with open(config_path, "w") as f:
			f.write(self.model_dump_json(indent=4))
			f.flush()
			os.fsync(f.fileno())

	@classmethod
	def load(cls):
		config_path = CONFIG_PATH

		if config_path.exists():
			with open(config_path, "r") as f:
				# Open the file and parse the JSON into the class
				data = json.load(f)
				return cls(**data)

		return cls()


def format_link(text, url) -> str:
	"""For Windows Terminal output, this allows URLs to be clickable links."""
	start = "\x1b]8;;"
	middle = "\x1b\\"
	end = "\x1b]8;;\x1b\\"
	return f"{start}{url}{middle}{text}{end}\n"


def get_url(platform: str, handle: str = ""):
	"""Creates a URL from a social media handle corresponding to the platform it belongs to."""
	no_at = ""
	if handle is not None: no_at = handle.replace("@", "", 1)
	match platform:
		case "Twitter":
			return f"https://twitter.com/{no_at}"
		case "BlueSky":
			return f"https://bsky.app/profile/{no_at}"
		case "Facebook":
			return f"https://www.facebook.com/{no_at}"
		case "Instagram":
			return f"https://www.instagram.com/{no_at}"
		case _:
			return None


def pair(arg_string: str) -> Tuple[str, str]:
	"""Create a tuple from a string 'argA:argB'. Used for parsing cmd line input."""
	arg_string = arg_string.strip()
	parts = arg_string.split(':', 1)  # Split along the =

	if len(parts) != 2: raise argparse.ArgumentTypeError(f"'{arg_string}' must be 'Platform:Handle'.")
	return parts[0], parts[1]


def get_pathstring_with_parent(path: Path) -> str:
	"""Returns the name of a path's parent dir along with its own name, e.g. 'files/file.txt'.
	Used to provide the user with a hint as to file locations, instead of just file names.
	:param path: Path object
	:returns: Path string: parent dir and file name
	"""
	if path == path.parent: return path.name  # Check if we're at the root of the filesystem.
	return path.parent.name + os.sep + path.name


if __name__ == "__main__":
	init(autoreset=True)  # Set up colorama text colors
	if sys.platform == 'win32': os.system('color')

	try:
		# Load settings and access our records.
		with Records(AppSettings.load()) as db:

			args = ArgHandler.get_args(db)

			# Invoke our argument handler
			if hasattr(args, "handler") and args.handler:
				args.handler(db, args)
			else:
				args.print_help()

	except KeyError as e:  # Usually bad user input or a record not found.
		print(f"Error processing request:")
		print(Fore.RED + f"\t{e}")
	except FileNotFoundError as e:
		print(Fore.RED + f"File {e.filename} not found.")
	except PermissionError as e:
		print(f"Error: Permission denied:")
		print("\t" + Fore.RED + f"{e.filename}")
	except sql.IntegrityError as e:
		print(Fore.RED + "That record already exists or violates a constraint.")
	except sql.OperationalError as e:
		print(Fore.RED + f"Database error: {e}")
	except sql.Error as e:  # catch-all for anything else sqlite-specific
		print(Fore.RED + f"Unexpected database error: {e}")
	except KeyboardInterrupt:
		print("Operation cancelled by user.")
		exit(1)
