# TestStripper.py
from __future__ import annotations
import argparse, os, re, time
from enum import IntEnum, StrEnum
from pathlib import Path
from colorama import Fore, init
import pyperclip
import sys
from timecode import Timecode

'''
This program strips the speaker labels and timecodes from a text file produced by Adobe Premiere Pro's
"Export to Text File" for transcribed video sequences. It can optionally replace speaker labels with proper names.
'''

# TODO: Error: when processing an entire directory (for merge/append), and
#  no output file was specified, use the dir name.

# TODO: Convert the timecodes regex system over to the timecode library.
# Regex matching timecodes, e.g. 00:01:22:08 - 00:01:38:09
TIMECODE_PATTERN = "^[0-9]{2}:[0-9]{2}:[0-9]{2}:[0-9]{2} - [0-9]{2}:[0-9]{2}:[0-9]{2}:[0-9]{2}"
DEFAULT_EXT = ".txt"  # Default filename extension
DEFAULT_LABEL = "Speaker"  # Default speaker input_label to match in transcripts.
SEPARATOR = "-"  # Used when appending several transcripts to a single output file, to delineate transcript names.
DEFAULT_UNIQUENAME = "stripped"



# Error codes for ParseFileException
class PFEErrorCode(IntEnum):
	NONEXISTANT = 1
	FILE_ERROR = 2
	SPEAKER_ERROR = 3


# Handler for command line args defining how to treat timecodes in a transcript
class TimecodeHandlerType(StrEnum):
	TC_REMOVE = "R"
	TC_ZERO = "Z"
	TC_PRESERVE = "P"


# TODO: Build some sort of speaker socials_db class that removes need for this global variable.
speaker_arg_counter = 0  # Incremented with each new speaker in arguments.


class ParseFileException(Exception):
	"""Exception thrown when the processFile function can't process a transcript file.
	Wrapper around several file i/o exceptions"""

	def __init__(self, message: str, code: int, line_num=0, line=""):
		super().__init__(message)
		self.code = code
		self.line_num = line_num
		self.line = line


def global_exception_handler(exctype, value, traceback):
	"""Error handler for global exceptions."""
	# Check if a debugger is attached (Developer Mode)
	if sys.gettrace() is not None:
		# Fall back to Python's default behavior so developers see the crash
		sys.__excepthook__(exctype, value, traceback)
		return
	# Present a clean, non-technical message to the end user
	print("\n[!] Something went wrong on our end.")
	print("The error has been logged, and our team will look into it. Please try again later.\n")
	sys.exit(1)


# Register the global handler
sys.excepthook = global_exception_handler

#TODO: This math is all wrong.
def zero_timecode(current: str, starting: str) -> str:
	"""Subtracts timecode strings. Strings are in the format found in lines from Adobe transcriptions, e.g.
	'00:03:00:13 - 00:03:19:02'
	"""
	# Check strings for proper format.
	if not re.search(TIMECODE_PATTERN, current):
		raise ValueError(f"Invalid timecode: '{current}'")
	if not re.search(TIMECODE_PATTERN, starting):
		raise ValueError(f"Invalid timecode: '{starting}'")

	# Split first and second timecodes into a list.
	current_list = current.strip().split(" - ", 2)
	starting_list = starting.strip().split(" - ", 2)

	# TODO: Inlude framerate as cmd line param?
	# Convert to a list of Timecode times.
	tc_start = [Timecode('24', "00:" + current_list[0]), Timecode('24', "00:" + current_list[1])]
	tc_end = [Timecode('24', "00:" + starting_list[0]), Timecode('24', "00:" + starting_list[1])]

	# Return a new string matching Adobe transcription's format.
	time_result = ""
	try:
		time_result = f"{tc_end[0] - tc_start[0]} - {tc_end[1] - tc_start[1]}"
	except ValueError as e:
		if "not 0" in e.args[0]:
			time_result = "00:00:00:00 - 00:00:00:00"
		else:
			raise
	finally:
		return time_result


def get_unique_filename(original_path: Path, suffix: str = DEFAULT_UNIQUENAME) -> Path:
	"""Takes a path. If a file with the same name already exists there, return a path with suffix, and
	possibly a number, appended to the filename such that a path to a unique, nonexistant filename is returned.
	:returns: Path to the unique file."""

	# Test existance and try to return before looping.
	if not original_path.exists(): return original_path

	# Strip trailing _NNN from original_path.
	split_filename = re.split(r"_(\d+)$", original_path.stem, maxsplit=1)

	# append suffix to base_stem, and try to exit before looping.
	new_path = original_path.parent / f"{split_filename[0]}_{suffix}{original_path.suffix}"
	if not new_path.exists(): return new_path

	counter = 1
	# If it already had a number, start our counter one higher
	if len(split_filename) > 1: counter = int(split_filename[1]) + 1

	# Test if file with the name exists, and increment the trailing number till a unique file is found.
	while new_path.exists():
		new_path = original_path.parent / f"{split_filename[0]}_{suffix}_{counter}{original_path.suffix}"
		counter += 1

	return new_path


def get_filename_header(filename: str) -> str:
	"""Creates a string from a filename with separator text on the lines before and after the filename.
	Used in writing multiple stripped transcript files to a single output file."""
	header = SEPARATOR * len(filename) + "\n"
	header += filename + "\n"
	header += SEPARATOR * len(filename) + "\n"
	return header


def get_pathstring_with_parent(path: Path) -> str:
	"""Returns the name of a path's parent dir along with its own name, e.g. 'files/file.txt'.
	Used to provide the user with a hint as to file locations, instead of just file names.
	:param path: Path object
	:returns: Path string: parent dir and file name
	"""
	if path == path.parent: return path.name  # Check if we're at the root of the filesystem.
	return path.parent.name + os.sep + path.name


def speaker_pair(arg_string: str):
	"""Converts cmd line arguments '-s 1=NameA 2=NameB' or '-s NameA NameB' into a ('Label', 'Name') tuple."""
	global speaker_arg_counter
	speaker_arg_counter += 1
	arg_string = arg_string.strip()

	if re.search(r"(\d+)=", arg_string):  # Find pattern, e.g. '1=John'
		parts = arg_string.split('=', 1)  # Split along the =
		if len(parts) != 2: raise argparse.ArgumentTypeError(f"'{arg_string}' must be 'XXX=Name' or just 'Name'.")
		label = f"{DEFAULT_LABEL} " + parts[0]  # Use our default input_label
		return label, parts[1]
	else:
		return f"{DEFAULT_LABEL} {speaker_arg_counter}", arg_string


def is_transcript(path: Path) -> bool:
	"""Verify that a file is a valid transcript by checking if the first line is a timecode.
	:param path: Path object"""
	if path.is_file():
		try:  # Read the first line and try to match it to the timecode pattern
			with open(path.resolve(), 'r', encoding='utf-8') as file:
				line = file.readline()
				return bool(re.search(TIMECODE_PATTERN, line))

		except FileNotFoundError:
			raise ParseFileException(f"File doesn't exist: '{get_pathstring_with_parent(path)}'",
									 PFEErrorCode.NONEXISTANT)
		except (PermissionError, OSError, UnicodeDecodeError) as e:
			raise ParseFileException(f"{e}",
									 PFEErrorCode.FILE_ERROR)
	return False


def strip_transcript(path: Path, speaker_map: dict, timecodes=TimecodeHandlerType.TC_REMOVE,
					 speaker_label=DEFAULT_LABEL) -> tuple[dict, str]:
	"""
	Reads through a transcript file, replaces speaker labels with proper names, and,
	optionally, strips timecodes. Writes the processed transcript to a file.
	:param path: Path to the transcript file to read from.
	:param timecodes: True if timecodes should be preserved in the output
	:param speaker_map: Mapping from speaker labels to speaker names.
	:param speaker_label: Label to match speaker names against.
	:return: Tuple[dict, str]: dict(Label, Name) representing the speakers found in the transcript, and
	a string containing the processed text.
	:raises ProcessFileException: If processing fails.
	"""
	found_speakers = dict()  # Keep a ledger of input_label/speaker pairs found in this transcript.
	first_timecode = ""
	try:

		with open(path.resolve(), 'r', encoding='utf-8') as file:
			output = ""  # Buffer for the processed text

			for line_num, line in enumerate(file, start=1):
				line = line.strip()

				if line == "":
					output += "\n"
					continue

				# Check if the line is a timecode
				if re.search(TIMECODE_PATTERN, line):
					if first_timecode == "": first_timecode = line.strip()
					match timecodes:
						case TimecodeHandlerType.TC_REMOVE:
							continue #Do nothing, just continue to next line.
						case TimecodeHandlerType.TC_ZERO:
							output += zero_timecode(line, first_timecode) + "\n"
						case TimecodeHandlerType.TC_PRESERVE:
							output += line + "\n"
					continue

				# Check if line is a speaker input_label
				if re.match(rf"^{speaker_label} (\d+)", line):
					if line in speaker_map:  # Speaker input_label found in speaker_map
						if not line in found_speakers: found_speakers[line] = speaker_map[line]
						output += speaker_map[line] + "\n"
						continue
					else:  # We've encountered an unidentified speaker.
						raise ParseFileException(f"Improper speaker input_label '{line}'",
												 code=PFEErrorCode.SPEAKER_ERROR, line_num=line_num, line=line)

				# Line isn't a speaker input_label or timecode, so just append it to the output.
				output += line + "\n"

			return found_speakers, output

	except FileNotFoundError as e:
		raise ParseFileException(f"File doesn't exist: '{e.filename}'", PFEErrorCode.NONEXISTANT)

	except (PermissionError, OSError, UnicodeDecodeError) as e:
		raise ParseFileException(f"Read error for '{e.filename}'", PFEErrorCode.NONEXISTANT)


def get_args():
	"""Parses command line arguments."""
	parser = argparse.ArgumentParser(description=f'Removes timecodes from a text file produced by '
												 'Adobe Premiere Pro\'s "Export to Text File" for transcribed '
												 'video sequences. Can optionally replace speaker labels '
												 f'(e.g. \'{DEFAULT_LABEL} 1\') with proper names, and consolidate '
												 f'multiple transcripts into one output file.')
	parser.add_argument("path", type=Path, nargs='?', default=Path.cwd(),
						help="path to transcript file or directory containing transcript files. Supports"
							 "wildcard '*' matching.")
	parser.add_argument("-e", "--extension", type=str, default=DEFAULT_EXT,
						help=f"filename extension for directory processing, default is '{DEFAULT_EXT}'")
	parser.add_argument("-p", "--append", type=str, default=DEFAULT_UNIQUENAME,
						help=f"append suffix to output filenames. Defualt is '{DEFAULT_UNIQUENAME}'")
	parser.add_argument("-o", "--output", type=Path,
						help="output filename or directory. Can be relative to input directory.")
	parser.add_argument("-r", "--recursive", default=False, action="store_true",
						help="search subdirectories recursively for transcript files.")
	parser.add_argument("-s", "--speakers", default=[], type=speaker_pair, action="append",
						nargs='+', help="speaker input_label and name, e.g. '1=John' or just 'John' "
										"(with automatic numbering).")
	parser.add_argument("-x", "--overwrite", default=False, action="store_true",
						help="overwrite existing files")
	parser.add_argument("-l", "--input_label", type=str, default=DEFAULT_LABEL,
						help=f"speaker input_label (to match in transcripts). Default is '{DEFAULT_LABEL}'")
	parser.add_argument("-ex", "--extra", default=[], type=str, action="append",
						nargs='+', help="extra speaker names for missing speakers.")
	parser.add_argument("-t", "--timecodes", type=str,
						choices=[TimecodeHandlerType.TC_ZERO, TimecodeHandlerType.TC_REMOVE,
								 TimecodeHandlerType.TC_PRESERVE],
						default=TimecodeHandlerType.TC_REMOVE, metavar="LETTER",
						help="How to handle timecodes. R: Remove, Z: Zero-ize (First tc "
							 "is set to 0:00), P: Preserve.")
	# TODO: Create an argument for non-interactive. "force"
	return parser.parse_args()


def main(args):

	# Get arguments from argparse into local variables
	# TODO: Do we need this? Would it make more sense just to reference args.xxxx?
	arg_ext = args.extension
	arg_timecodes = args.timecodes
	arg_overwrite = args.overwrite
	arg_recursive = args.recursive
	arg_label = args.input_label
	arg_inpath = args.path
	arg_extra = args.extra
	arg_suffix = args.append

	# ----------------------------------
	# HANDLE SPEAKERS
	# ----------------------------------
	# Create speaker_map, populate with args or use a default entry.
	speaker_map = {}
	if args.speakers:
		for item in args.speakers:
			if isinstance(item, list):
				speaker_map.update(dict(item))  # Handles the action="append" list-of-lists
			else:
				speaker_map.update([item])  # Handles a simple list of tuples
	else:
		speaker_map = {f"{arg_label} 1": f"{arg_label} 1"}  # e.g. 'Speaker 1: Speaker 1'

	# If we've supplied an input_label argument, update all the labels in speaker_map
	if arg_label != DEFAULT_LABEL:
		arg_label = args.input_label.strip()
		new_map = dict()
		for key, value in speaker_map.items():
			new_map[f"{arg_label} {key.split(' ', 1)[1]}"] = value
		speaker_map = new_map

	# ----------------------------------
	# HANDLE INPUT PATH ARG
	# ----------------------------------
	# Check that the input path argument can be resolved on the file system.
	try:
		if arg_inpath.parent == Path("."):  # if it's just a filename, make parent cwd
			arg_inpath = Path.cwd() / arg_inpath
		arg_inpath.parent.resolve(strict=True)  # Strict: Input path must exist on the filesystem.
	except FileNotFoundError as e:
		print(Fore.RED + f"Input path is invalid: '{arg_inpath}'")
		exit(1)
	except (OSError, RuntimeError, PermissionError) as e:
		print(Fore.RED + f"Error: {e}")
		exit(1)

	# ----------------------------------
	# BUILD LIST OF INPUT FILES
	# ----------------------------------
	in_paths = list()
	if arg_inpath.is_dir():
		if arg_recursive:
			in_paths = list(arg_inpath.rglob(f"*{arg_ext}"))
		else:
			in_paths = list(arg_inpath.glob(f"*{arg_ext}"))
	else:
		if arg_recursive:
			in_paths = list(arg_inpath.parent.rglob(arg_inpath.name))
		else:
			in_paths = list(arg_inpath.parent.glob(arg_inpath.name))

	# ----------------------------------
	# HANDLE OUTPUT PATH
	# ----------------------------------
	arg_outpath = Path(args.output) if args.output else arg_inpath
	# TODO: Try to remove write_single_file and determine contextually instead.
	write_single_file = False  # This indicates that we're writing all input files to a single output file.
	try:
		if not arg_outpath.is_absolute():  # If out_path is relative, make it relative to input path
			arg_outpath = arg_inpath / arg_outpath if arg_inpath.is_dir() else arg_inpath.parent / arg_outpath
		arg_outpath = arg_outpath.resolve()
	except FileNotFoundError as e:
		print(Fore.RED + f"Output path is invalid: '{arg_outpath}'")
		exit(1)
	except (OSError, RuntimeError, PermissionError) as e:
		print(Fore.RED + f"Error: {e}")
		exit(1)
	# if outpath is a dir, make sure it exists
	# TODO: We're determining if a non-existant path is a dir based on the existance of a .xxx suffix. Not great.
	if not arg_outpath.suffix:
		arg_outpath.mkdir(parents=True, exist_ok=True)
	else:
		if len(in_paths) > 1: write_single_file = True

	# Set up some stats collection.
	success_list = list()  # Dict containing successfully processed file input and output pairs.
	fail_list: list[Path] = []  # List of input files that failed to process.
	start_time = time.perf_counter()  # Track time to complete processing.

	# ----------------------------------
	# CORRELATE INPUT AND OUTPUT FILES
	# ----------------------------------
	# Build a list of valid input and output file pairs.
	in_out_paths = []
	for path in in_paths:
		try:
			if not is_transcript(path): continue  # First, check if we're looking at a valid transcript file.

			# TODO: Too many nests. clean up logic.
			if arg_outpath.is_dir():
				if arg_overwrite:
					if arg_inpath.is_dir():
						in_out_paths.append((path, arg_outpath / path.relative_to(arg_inpath)))
					else:
						in_out_paths.append((path, arg_outpath / path.relative_to(arg_inpath.parent)))
				else:
					if arg_inpath.is_dir():
						in_out_paths.append((path, get_unique_filename(arg_outpath / path.relative_to(arg_inpath),
																	   arg_suffix)))
					else:
						in_out_paths.append((path, get_unique_filename(arg_outpath /
																	   path.relative_to(arg_inpath.parent),
																	   arg_suffix)))
			else:
				if arg_overwrite:
					in_out_paths.append((path, arg_outpath))
				else:
					in_out_paths.append((path, get_unique_filename(arg_outpath), arg_suffix))
		except ParseFileException as e:  # This exception wraps together several  i/o exceptions.
			print(Fore.RED + f"Error reading {get_pathstring_with_parent(path)}.")
			fail_list.append(path)
			continue

	if len(in_out_paths) == 0:  # Double-check to make sure we've identified some transcripts.
		print(Fore.RED + f"No transcript files found.")
		exit(0)

	# ----------------------------------
	# PROCESS EACH INPUT/OUTPUT PAIR
	# ----------------------------------
	# Now, parse each file pair
	for in_file, out_file in in_out_paths:

		max_extra_speaker = 0
		print(f"{get_pathstring_with_parent(in_file)}:")

		# Handle the overwrite argument. Create a unique filename for out_file if needed.
		if arg_overwrite:
			print(Fore.RED + f"\tOverwriting '{get_pathstring_with_parent(out_file)}'.")
		# TODO: Fix this when I implement my file list class. We need to see if we've created a unique file or not.
		# elif in_file.samefile(out_file):
		#	print(Fore.RED + f"\tFile already exists, writing instead to: "
		#					 f"'{get_pathstring_with_parent(out_file)}'.")

		# Try processing the transcript. This loop is here to handle unidentified speakers. If a speaker can't be
		# identified, ParseFileException is raised. Prompt for speaker name or use the default speaker, and reprocess.
		# New added speaker names will be used in subsequent processing.
		success = False
		while not success:
			try:
				found_speakers, out_string = strip_transcript(in_file, speaker_map, timecodes=arg_timecodes,
															  speaker_label=arg_label)
				lines = len(out_string.splitlines())

				# Write to separate files or append to one file, depending on arg_outpath.
				out_file.parent.mkdir(parents=True, exist_ok=True)
				if write_single_file:
					with open(out_file, 'a', encoding='utf-8') as file:
						if len(success_list) == 0: file.truncate(0)  # Clear out_file if this is first file.
						# Add header text for each new input transcript.
						file.write(get_filename_header(in_file.stem))
						file.write(out_string)  # Else there's just one input file, so don't use

						pyperclip.copy(out_string)  # Add to system clipboard.
				else:  # arg_outpath doesn't point to a dir, so every intput file appends to the same output. Append.
					with open(out_file, 'w', encoding='utf-8') as file:
						file.write(out_string)

				# Successfully processed and wrote transcript!
				success = True  # Exit the while loop
				success_list.append((in_file, out_file))  # Add to ledger of successfully processed files.
				# Print a little report for this transcript.
				print(f"\tSuccessfully processed '{get_pathstring_with_parent(in_file)}'")
				names = [found_speakers[k] for k in sorted(found_speakers)]
				total_speakers = len(found_speakers)
				if total_speakers > 0:
					print(
						f"\tFound " + Fore.CYAN + F"{total_speakers} " + Fore.RESET +
						f"speaker{"" if total_speakers == 1 else "s"}: " + Fore.CYAN + f"{", ".join(names)}")
				print(f"\tWrote " + Fore.CYAN + f"{lines}" + Fore.RESET + " lines to " + Fore.CYAN +
					  f"'{get_pathstring_with_parent(out_file)}'\n")

			except ParseFileException as e:
				if e.code == PFEErrorCode.SPEAKER_ERROR:  # We've found a missing speaker! Add an entry to speaker_map
					name = e.line
					print(Fore.RED + f"\tMissing speaker '{e.line}' at line {e.line_num}.")
					if arg_extra:
						test_speaker_num = 0  # <-- Make sure we don't overwrite an existing speaker name.
						while arg_label + " " + str(test_speaker_num) in speaker_map:
							test_speaker_num += 1
						name = arg_extra[max_extra_speaker]
						max_extra_speaker += 1
						name = input(f"\tName for {e.line}: ")

					speaker_map[e.line] = name  # Create a new entry in speaker_map
				# Now return to while loop and re-process file with the updated speaker_map

				else:  # Handle other errors.
					print(Fore.RED + f"Error while processing file: '{get_pathstring_with_parent(in_file)}'"
									 f"\n\t{str(e)}\n")
					fail_list.append(in_file)
					continue

			# ParseFileException wraps file i/o errors for the input file, so these are only raised when writing.
			except FileNotFoundError as e:
				print(Fore.RED + f"Output file doesn't exist: '{get_pathstring_with_parent(out_file)}'"
								 f"\n\t{str(e)}\n")
				fail_list.append(in_file)
				continue
			except PermissionError as e:
				print(Fore.RED + f"Improper permissions for output file: '{get_pathstring_with_parent(out_file)}'"
								 f"\n\t{str(e)}\n")
				fail_list.append(in_file)
				continue
			except OSError as e:
				print(Fore.RED + f"Filesystem Error for output file: {e}")
				fail_list.append(in_file)
				continue

	# Calculate time taken to process files.
	end_time = time.perf_counter()

	# Finished processing all files, print results.
	print(Fore.CYAN + "----- REPORT -----")
	print(f"Total processing time: {(end_time - start_time):.3f} seconds.\n")
	print(f"Successfully processed {len(success_list)} {"files" if len(success_list) != 1 else "file"}:")

	# TODO: If we're writing to one output file, don't give a big list of files here. Just # of files and the output.
	for pair in success_list: print(f"\t{get_pathstring_with_parent(pair[0])}" + Fore.CYAN + " ---> " +
									Fore.RESET + f"{get_pathstring_with_parent(pair[1])}")

	if len(fail_list) > 0:
		print(Fore.RED + f"Failed to process {len(fail_list)} {"files" if len(fail_list) != 1 else "file"}:")
		for path in fail_list: print(Fore.RED + f"\t{get_pathstring_with_parent(path)}")


# ------------------- MAIN -------------------
if __name__ == "__main__":
	try:
		init(autoreset=True)  # Set up colorama text colors
		main(get_args())
	except KeyboardInterrupt:
		print(Fore.RED + "Operation cancelled by user.")
		exit(1)
