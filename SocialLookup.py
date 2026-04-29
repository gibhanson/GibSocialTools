# SocialLookup.py
from __future__ import annotations
import datetime
import json
import os, sys, argparse, hashlib
from urllib.parse import urlparse
from pathlib import Path
from typing import Tuple, Type, Any
from polars import col, DataFrame
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

# TODO: Add a timestamp to show when last record update
# TODO: Build a tester

CONFIG_PATH = Path(__file__).resolve().parent / "sociallookup_config.json"  # By default, look next to this py file.


class Records:
	"""Handles the reading and writing of a .csv database of social media records."""

	data: pl.DataFrame
	config: AppSettings

	def __init__(self, settings: AppSettings):
		self.config = settings
		self.data = pl.DataFrame()
		# self.schema = {"ID": pl.String,	"Name": pl.String, "Time": pl.Datetime,
		# 			   **{col: pl.String for col in self.config.platform_names}}

	def __enter__(self) -> 'Records':
		self.load()
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.save()

	def __str__(self):
		return str(self.data)

	def load(self):
		if Path(self.config.database_path).exists():
			self.data = pl.read_csv(self.config.database_path, infer_schema_length=0)
			self.data = self.data.with_columns(pl.col("Time").str.to_datetime(strict=False))

		else:
			raise FileNotFoundError(f"{self.config.database_path}", self.config.database_path)

	# def sync_schema(self):
	# 	existing_cols = self.data.columns
	# 	missing_cols = [p for p in self.config.platform_names if p not in existing_cols]
	#
	# 	if missing_cols:
	# 		print(f"Syncing Schema: Adding {missing_cols} to database.")
	# 		self.data = self.data.with_columns([pl.lit(None).alias(col) for col in missing_cols])
	# 		self.save()

	def save(self):
		"""Saves both the database and config file."""
		self.config.save()
		self.data.write_csv(self.config.database_path)

	def print_records(self, data: DataFrame):
		"""Prints out a record in an easily readable form.
		:param data: Dataframes containing records to print.
		"""
		init(autoreset=True)  # Set up colorama text colors

		for index, row in enumerate(data.iter_rows(named=True)):
			print(Fore.GREEN + f"{row['Name']}: " + Fore.RESET + f"[{row['ID']}] {row["Time"].
				  strftime('%a %b %d, %Y (%H:%M:%S)')}")
			for col in data.columns:
				if col in self.config.platform_names:
					social_list_index = self.config.platform_names.index(col)
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


	def get_all(self) -> DataFrame:
		"""Returns a DataFrame containing ALL records from the database."""
		return self.data


	def add(self, name: str, socials_dict: dict) -> str:
		"""
		Updates a record with modified social handles, or creates a new record
		if a record for 'name' doesn't exist.
		:param name: The name of the record.
		:param socials_dict: dictionary of social records to add. (Platform Name: Handle)
		:returns: the ID of added/modified record.
		"""
		hash_id = Records.generate_id(name)
		now = datetime.datetime.now()
		updates = {'Name': name, 'ID': hash_id, "Time": now}

		for col in self.data.columns:
			if col in self.config.platform_names:
				if col in socials_dict:
					updates[col] = socials_dict[col]
				else:
					# noinspection PyTypeChecker
					updates[col] = None


		if hash_id in self.data["ID"]:
			# UPDATE: Apply the changes only to the row with this ID
			expressions = [
				pl.when(pl.col("ID") == hash_id)
				.then(
					# Inner logic: Only update if the new value is NOT None
					pl.when(pl.lit(val).is_not_null())
					.then(pl.lit(val))
					.otherwise(pl.col(key))
				)
				.otherwise(pl.col(key))  # For every other row in the DB, keep the data
				.alias(key)
				for key, val in updates.items()
			]

			self.data = self.data.with_columns(expressions)
		else:
			new_row = pl.DataFrame([updates])
			new_row = new_row.select(self.data.columns)
			new_row = new_row.cast(self.data.schema)

			self.data = self.data.vstack(new_row)

		return hash_id


	def remove(self, name: str, platforms: list) -> DataFrame:
		"""
		Removes the handle for a particular platform from a record.
		:param name: The name of the record to remove.
		:param platforms: The list of platforms to remove.
		:returns: A dataframe containing the updated record.
		:raises KeyError: if 'name' doesn't exist.
		"""
		if name not in self.data["Name"]:
			raise KeyError(f"'{name}' not found in database.")

		hash_id = Records.generate_id(name)
		updates = {'Name': name, 'ID': hash_id}

		for platform in platforms:
			if platform in self.config.platform_names:
				self.data = self.data.with_columns(
					pl.when(pl.col("ID") == hash_id)
					.then(pl.lit(None))
					.otherwise(pl.col(platform))
					.alias(platform)
				)

		return self.data.filter(col("ID") == hash_id)


	def delete(self, name: str) -> DataFrame:
		"""
		Remove a record from the database based on name.
		:param name: The name of the record to remove.
		:returns: A copy of the removed record.
		:raises KeyError: if 'name' doesn't exist.
		"""
		if name not in self.data["Name"]:
			raise KeyError(f"'{name}' not found in database.")

		hash_id = self.data.filter(pl.col("Name") == name).select("ID").item()
		removed = self.drop(hash_id)

		if removed.is_empty: raise KeyError(f"ID '{hash_id}' not found in database.")
		else: return removed


	def drop(self, hash_id: str) -> DataFrame:
		"""
		Remove a record from the database based on a hash ID.
		:param hash_id: The name of the record to remove.
		:returns: A copy of the removed record.
		:raises KeyError: if 'name' doesn't exist.
		"""
		record = self.data.filter(pl.col("ID") == hash_id)

		if record.height == 0:
			raise KeyError(f"'{hash_id}' not found in database.")
		elif record.height > 1:
			raise KeyError(f"'{hash_id}' returned too many records ({record.height}).")

		self.data = self.data.filter(pl.col("ID") != hash_id)
		return record


	def get_by_name(self, name: str) -> DataFrame:
		"""
		Returns a record from the database based on a name. 'name' must be an exact
		match in the database. (case-insensitive).
		:param name: Name of the record to return.
		:return: DataFrame containing the record from the database.
		:raises KeyError: if 'name' doesn't exist in the database, or if the database is corrupt and
		multiple records match the name.
		"""
		record = self.data.filter(pl.col("Name").str.to_lowercase() == name.lower())
		if record.is_empty:	raise KeyError(f"'{name}' not found in database.")
		else: return record


	def get_id(self, name: str) -> str:
		"""
		Returns the hash ID of a record from the database based on a name.
		:param name: Name of the record to look up.
		:returns: Hash ID of the record from the database.
		:raises KeyError: if 'name' doesn't exist in the database, or if the database is corrupt and
		multiple records match the name.
		"""
		record = self.data.filter(pl.col("Name").str.to_lowercase() == name.lower())
		if record.height == 0:
			raise KeyError(f"'{name}' not found in database.")
		elif record.height > 1:
			raise KeyError(f"'{name}' returned too many records ({record.height}).")

		return record.item(0, "ID")


	def search_single(self, name: str) -> DataFrame:
		"""
		Performs a fuzzy search of the database's 'name' column and returns the BEST match.
		:param name: Name of the record to look up.
		:returns: DataFrame containing the record from the database.
		"""
		choices = self.data['Name'].to_list()
		results = process.extractOne(name, choices, scorer=fuzz.token_set_ratio)
		matched_names = [match[0] for match in results]

		return self.data[self.data['Name'].is_in(matched_names)].clone()


	def search(self, name: str, cutoff: int = None) -> DataFrame:
		"""
		Performs a fuzzy search of the database's 'name' column and returns ALL matches with
		similarities greater than 'cutoff'.
		:param name: Name of the record to look up.
		:param cutoff: Number between 0 and 100 describing a similarity tolerance. 0 is dissimilar and 100 is exact.
		:return: DataFrame containing the records from the database.
		"""
		if not cutoff: cutoff = self.config.score_cutoff

		choices = self.data['Name'].to_list()
		results = process.extractBests(name, choices, scorer=fuzz.token_set_ratio, score_cutoff=cutoff)
		matched_names = [r[0] for r in results]

		return self.data.filter(pl.col("Name").is_in(matched_names))


	def get_by_id(self, id_hash: str) -> DataFrame:
		"""Returns a record from the database based on a hash ID.
		:param id_hash: The hash ID of the record to look up.
		:returns: DataFrame containing the record from the database.
		:raises KeyError: if 'id_hash' doesn't exist in the database.
		"""
		record = self.data.filter(pl.col("ID") == id_hash)
		if record.is_empty(): raise KeyError(f"'{id_hash}' not found in database.")
		else: return record


	@staticmethod
	def generate_id(name: str) -> str:
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

		if isinstance(args.name, list): # Make it so the name parameter doesn't need to be in quotation marks
			args.name = " ".join(args.name)

		return args

	@staticmethod
	def handle_add(db, args):

		if not args.name:
			raise ValueError("Name must be provided.")
		else:
			socials = dict()

			for item in args.add:
				entry = pair(item)
				socials[entry[0]] = entry[1]

			hash_id = db.add(args.name, socials)


			db.print_records(db.get_by_id(hash_id))

	@staticmethod
	def handle_list_all(db, args):
		# This one ignores the Name parameter entirely
		db.print_records(db.get_all())

	@staticmethod
	def handle_drop(db, args):
		if not args.name:
			raise ValueError("Name must be provided.")
		else:
			hash_id = db.get_id(args.name)
			db.drop(db.get_id(args.name))
			print("Removed " + Fore.CYAN + f"{args.name} ({hash_id}).")

	@staticmethod
	def handle_remove(db, args):
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
			db.print_records(record)

	@staticmethod
	def handle_id(db: Records, args):
		if not args.name:
			raise ValueError("Name must be provided.")
		else: db.get_by_id(args.name)

	@staticmethod
	def handle_default(db: Records, args):
		if not args.name:
			db.print_records(db.get_all())
		else:
			found = db.search(args.name)
			if found.height > 0:
				db.print_records(db.search(args.name))
			else:
				print("Error: No records found.")


class AppSettings(BaseSettings):
	"""Manages reading and writing of a json file containing default settings."""
	#These are default settings if a .json can't be found.
	database_path: Path = Field(default=Path(__file__).resolve().parent / "socials.csv")
	score_cutoff: int = Field(default=70, ge=0, le=100)  # ge=0 means "greater than or equal to 0"
	platform_names: list[str] = ["Twitter", "BlueSky", "Facebook", "Website", "Description"]
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
		case _:
			return None


def pair(arg_string: str) -> Tuple[str, str]:
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


def main(args):

	try:
		with Records(AppSettings.load()) as db:
			if hasattr(args, "handler") and args.handler:
				args.handler(db, args)
			else:
				args.print_help()

	except KeyError as e:
		print(f"Error processing request:")
		print(Fore.RED + f"\t{e}")
	except FileNotFoundError as e:
		print(Fore.RED + f"File {e.filename} not found.")
	except PermissionError as e:
		print(f"Error: Permission denied:")
		print("\t" + Fore.RED + f"{e.filename}")
	except pl.exceptions.NoDataError as e:
		print("Error: The CSV file exists but is empty or corrupt:")
		print("\t" + Fore.RED + str(db.config.database_path))


if __name__ == "__main__":
	if sys.platform == 'win32': os.system('color')

	try:
		main(ArgHandler.get_args())
	except KeyboardInterrupt:
		print("Operation cancelled by user.")
		exit(1)
