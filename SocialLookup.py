# SocialLookup.py
from __future__ import annotations
import json
import os, sys, argparse, hashlib
from urllib.parse import urlparse
from pathlib import Path
from typing import Tuple, Type, Any
from polars import col, lit, DataFrame
from thefuzz import process, fuzz
import polars as pl
from colorama import Fore, init
from pydantic import Field
from pydantic_settings import (
	BaseSettings,
	PydanticBaseSettingsSource,
	SettingsConfigDict,
	JsonConfigSettingsSource
)


CONFIG_PATH = Path(__file__).resolve().parent / "sociallookup.json"  # Look next to this py file.


class Records:
	"""Handles the reading and writing of a database of social media records."""

	data: pl.DataFrame
	config: AppSettings
	social_columns: list[str]

	def __init__(self, settings: AppSettings):
		self.config = settings
		self.social_columns = [item.lower() for item in self.config.platform_names]
		self.data_file = self.config.database_path
		self.data = pl.DataFrame()
		self.schema = {"ID": pl.String,	"Name": pl.String, **{col.lower(): pl.String for col in self.social_columns}}

	def __enter__(self) -> 'Records':
		self.load()
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.save()

	def __str__(self):
		return str(self.data.to_struct())

	def load(self):
		if self.data_file.exists():
			self.data = pl.read_csv(self.data_file, schema=self.schema, null_values="", encoding="utf-8",
									infer_schema_length=10000).with_columns([pl.col("ID").str.strip_chars(),
																			  pl.col("Name").str.strip_chars()])
			self.sync_schema(self.social_columns)
		else:
			self.data = pl.DataFrame({"ID": [], "Name": [], **{col: [] for col in self.social_columns}})
			self.data.write_csv(self.data_file)
			self.sync_schema(self.social_columns)

	def sync_schema(self, expected_platforms: list[str]):
		# 1. Determine what's missing
		existing_cols = self.data.columns
		missing_cols = [p for p in expected_platforms if p not in existing_cols]

		if missing_cols:
			print(f"Syncing Schema: Adding {missing_cols} to database.")
			self.data = self.data.with_columns([pl.lit(None).alias(col) for col in missing_cols])
			self.save()

	def save(self):
		self.config.save()
		self.data.write_csv(self.data_file)

	def print_records(self, data: DataFrame):
		init(autoreset=True)  # Set up colorama text colors

		for index, row in enumerate(data.iter_rows(named=True)):
			print(Fore.GREEN + f"{row['Name']}:" + Fore.RESET + f"{row['ID']}")
			for col in data.columns:
				if col in self.social_columns:
					social_list_index = self.social_columns.index(col)
					platform = self.config.platform_names[social_list_index]
					if row[col] is not None:
						handle = ""
						url = ""
						if platform == "website":
							url = row[col]
							parts = urlparse(url)
							handle = f"{parts.netloc}{parts.path}"
						else:
							handle = row.get(col)
							url = get_url(platform, handle)

						if url and "WT_SESSION" in os.environ:
							sys.stdout.write(Fore.CYAN + f"\t{platform}: " + Fore.RESET + f"{format_link(handle, url)}")
							sys.stdout.flush()
						else:
							print(Fore.CYAN +f"\t{platform}: " + Fore.RESET + f"{handle}")

	def update_setting(self, key: str, value: Any):
		"""Updates a setting, validates it, and saves to sociallookup.json."""
		current_data = self.config.model_dump()

		if key not in current_data:
			raise KeyError(f"'{key}' is not a valid setting.")

		current_data[key] = value
		self.config = AppSettings(**current_data)

		with open("config.json", "w") as f:
			f.write(self.config.model_dump_json(indent=4))

		self.data_file = self.config.database_path
		self.config.save()

	def get_all(self) -> DataFrame:
		"""Returns a DataFrame containing ALL records."""
		return self.data

	def add(self, name: str, socials_dict: dict) -> str:
		"""Adds or updates a record."""

		hash_id = Records.generate_id(name)
		updates = {'Name': name, 'ID': hash_id}

		for social, handle in socials_dict.items():
			key = social.lower()
			if key in self.data.columns:
				updates[key] = handle
			else: raise KeyError(f"'{social}' is not a valid record.")

		if hash_id in self.data["ID"]:
			# UPDATE: Apply the changes only to the row with this ID
			expressions = [
				pl.when(pl.col("ID") == hash_id)
				.then(pl.lit(val))  # Wrap in lit() here, once.
				.otherwise(pl.col(key))
				.alias(key)
				for key, val in updates.items()
			]
			self.data = self.data.with_columns(expressions)
		else:
			new_row = pl.DataFrame([updates])
			new_row = new_row.select(self.data.columns)
			# Force the new row to match the existing schema (String vs Object fix)
			new_row = new_row.cast(self.data.schema)

			# 4. Now vstack will be happy
			self.data = self.data.vstack(new_row)

		return hash_id

	def remove(self, name: str, platforms: list) -> DataFrame:
		if name not in self.data["Name"]:
			raise KeyError(f"'{name}' not found in database.")

		hash_id = self.data.filter(pl.col("Name") == name).select("ID").item()

		[item.lower() for item in self.config.platform_names]

		#TODO: create a version of platform_names that's lowercase, like the old SOCIAL_COLUMNS
		social_platforms = [i.lower() for i in platforms if i in self.config.platform_names]

		for item in social_platforms:
			self.data = self.data.with_columns(
				pl.when(col("ID") == hash_id)
				.then(lit(""))  # Set to empty string
				.otherwise(col(item.lower()))  # Keep existing value for everyone else
				.alias(item.lower())  # Save it back into the same column name
			)

		return self.data.filter(col("ID")).clone()

	def delete(self, name: str) -> DataFrame:
		if name not in self.data["Name"]:
			raise KeyError(f"'{name}' not found in database.")

		hash_id = self.data.filter(pl.col("Name") == name).select("ID").item()
		removed = self.drop(hash_id)

		if removed.is_empty: raise KeyError(f"ID '{hash_id}' not found in database.")
		else: return removed

	def drop(self, hash_id: str) -> DataFrame:
		record = self.data.filter(pl.col("ID") == hash_id)

		if record.height == 0:
			raise KeyError(f"'{hash_id}' not found in database.")
		elif record.height > 1:
			raise KeyError(f"'{hash_id}' returned too many records ({record.height}).")

		self.data = self.data.filter(pl.col("ID") != hash_id)
		return record

	def get_by_name(self, query: str) -> DataFrame:
		record = self.data.filter(pl.col("Name").str.to_lowercase() == query.lower())
		if record.is_empty:	raise KeyError(f"'{query}' not found in database.")
		else: return record

	def get_id(self, query: str) -> str:
		record = self.data.filter(pl.col("Name").str.to_lowercase() == query.lower())
		if record.height == 0:
			raise KeyError(f"'{query}' not found in database.")
		elif record.height > 1:
			raise KeyError(f"'{query}' returned too many records ({record.height}).")

		return record.item(0, "ID")

	def search_single(self, query: str, cutoff: int = None) -> DataFrame:
		if not cutoff: cutoff = self.config.score_cutoff

		choices = self.data['Name'].to_list()
		results = process.extractOne(query, choices, scorer=fuzz.token_set_ratio, score_cutoff=cutoff)
		matched_names = [match[0] for match in results]

		return self.data[self.data['Name'].is_in(matched_names)].clone()

	def search(self, query: str, cutoff: int = None) -> DataFrame:
		if not cutoff: cutoff = self.config.score_cutoff

		choices = self.data['Name'].to_list()
		results = process.extractBests(query, choices, scorer=fuzz.token_set_ratio, score_cutoff=cutoff)
		matched_names = [r[0] for r in results]

		return self.data.filter(pl.col("Name").is_in(matched_names))

	def get_by_id(self, id_hash: str) -> DataFrame:
		record = self.data.filter(pl.col("ID") == id_hash)
		if record.is_empty(): raise KeyError(f"'{id_hash}' not found in database.")
		else: return record

	@staticmethod
	def generate_id(name: str) -> str:
		return hashlib.md5(name.lower().encode()).hexdigest()[:8].lower()


class ArgHandler:
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
	def get_args():
		"""Parses command line arguments."""
		parser = argparse.ArgumentParser(description=f"Social Media Lookup Utility. Retrieves and modifies "
													 f"social media information.")

		parser.add_argument("name", type=str, nargs="*", default=None,
							help=f"Name of person to look up. If used without a parameter, perform a fuzzy search "
								 f"and displays all social media handles for matching persons. "
								 f"If no name is provided, prints the entire database.")

		group = parser.add_mutually_exclusive_group(required=False)

		group.add_argument("-a", "--add", nargs="+", action=ArgHandler.HandleAddAction,
						   help="Add or update a social record (e.g. \"Twitter=@handle Bluesky=@handle\"). "
								"Requires that the Name parameter be exact.")

		group.add_argument("-r", "--remove", type=str, nargs='+', action=ArgHandler.HandleRemoveAction,
						   help="Delete social record. Requires that the Name parameter be exact.")

		group.add_argument("-d", "--drop", default=False, action="store_const",
						   const=ArgHandler.handle_drop, dest="handler",
						   help="Delete an entire entry. Requires that the Name parameter be exact.")

		group.add_argument("-id", "--id", nargs=1, action=ArgHandler.HandleIDAction, metavar="ID",
						   help="Retrieve the hash ID of a social record by name. "
								"Requires that the Name parameter be exact.")

		group.add_argument("-c", "--cutoff", type=int, default=70,
						   help="Search cutoff for fuzzy searching (0 - 100). Lower is less strict. Default is 70.")

		parser.set_defaults(handler=ArgHandler.handle_default)

		args = parser.parse_args()

		if isinstance(args.name, list):
			args.name = " ".join(args.name)

		return args

	@staticmethod
	def handle_add(db, args):
		if not args.name:
			print("Error: Delete requires a Name.")
		else:
			socials = dict()

			for item in args.add:
				entry = pair(item)
				socials[entry[0]] = entry[1]
			try:
				hash_id = db.add(args.name, socials)
			except KeyError as e:
				print(e)
				return

			db.print_records(db.get_by_id(hash_id))

	@staticmethod
	def handle_list_all(db, args):
		# This one ignores the Name parameter entirely
		db.print_records(db.get_all())

	@staticmethod
	def handle_drop(db, args):
		if not args.name:
			print("Error: Delete requires a Name.")
		else:
			hash_id = db.get_id(args.name)
			db.drop(db.get_id(args.name))
			print("Removed " + Fore.CYAN + f"{args.name} ({hash_id}).")

	@staticmethod
	def handle_remove(db, args):
		if not args.name:
			print("Error: Remove requires a Name.")
			return
		if not args.remove:
			print("Error: Remove requires platform names.")
			return

		valid_platforms = {platform.lower() for platform in args.remove}.intersection(db.social_columns)

		if not valid_platforms:
			print("Error: Invalid platform names.")
		else:
			record = db.remove(args.name, valid_platforms)
			print("Updated Record:")
			db.print_record(record)

	@staticmethod
	def handle_id(db: Records, args):
		if not args.name: print("Error: Delete requires a Name.")
		else: db.get_by_id(args.name)

	@staticmethod
	def handle_default(db: Records, args):
		if not args.name: db.print_records(db.get_all())
		else: db.print_records(db.search(args.name))


class AppSettings(BaseSettings):
	# 1. Define fields with types and defaults
	database_path: Path = Field(default=Path(__file__).resolve().parent / "socials.csv")
	score_cutoff: int = Field(default=70, ge=0, le=100)  # ge=0 means "greater than or equal to 0"
	platform_names: list[str] = ["Twitter", "BlueSky", "Facebook", "Website"]
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
			# Open the file and parse the JSON into the class
			with open(config_path, "r") as f:
				data = json.load(f)
				return cls(**data)

		return cls()


def format_link(text, url) -> str:
	start = "\x1b]8;;"
	middle = "\x1b\\"
	end = "\x1b]8;;\x1b\\"
	return f"{start}{url}{middle}{text}{end}\n"


def get_url(platform: str, handle: str = ""):
	no_at = ""
	if handle is not None: no_at = handle.replace("@", "", 1)
	match platform.lower():
		case "twitter":
			return f"https://twitter.com/{no_at}"
		case "bluesky":
			return f"https://bsky.app/profile/{no_at}"
		case "facebook":
			return f"https://www.facebook.com/{no_at}"
		case _:
			return None


def pair(arg_string: str) -> Tuple[str, str]:
	arg_string = arg_string.strip()
	parts = arg_string.split(':', 1)  # Split along the =
	if len(parts) != 2: raise argparse.ArgumentTypeError(f"'{arg_string}' must be 'Platform:Handle'.")
	return parts[0].lower(), parts[1]


def get_pathstring_with_parent(path: Path) -> str:
	"""Returns the name of a path's parent dir along with its own name, e.g. 'files/file.txt'.
	Used to provide the user with a hint as to file locations, instead of just file names.
	:param path: Path object
	:returns: Path string: parent dir and file name
	"""
	if path == path.parent: return path.name  # Check if we're at the root of the filesystem.
	return path.parent.name + os.sep + path.name


def main(args):
	settings = AppSettings.load()

	try:
		with Records(settings) as db:
			if hasattr(args, "handler") and args.handler:
				args.handler(db, args)
			else:
				args.print_help()

	except KeyError as e:
		print(f"Error processing request:")
		print(Fore.RED + f"\t{e}")
	except FileNotFoundError as e:
		print(f"Error: The database file at " + Fore.RED + f"'{settings.database_path}'"
			  + Fore.RESET + " was not found.")
	except PermissionError:
		print(f"Error: Permission denied:")
		print("\t" + Fore.RED + str(settings.database_path.absolute()))
	except pl.exceptions.NoDataError:
		print("Error: The CSV file exists but is empty or corrupt:")
		print("\t" + Fore.RED + str(settings.database_path.absolute()))


if __name__ == "__main__":
	if sys.platform == 'win32': os.system('color')

	try:
		main(ArgHandler.get_args())
	except KeyboardInterrupt:
		print("Operation cancelled by user.")
		exit(1)
	except Exception as e:
		print(f"An unexpected error occurred: {e}")
