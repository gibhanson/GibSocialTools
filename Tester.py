# Tester.py
import inspect
import shutil
from pathlib import Path
from unittest.mock import patch
import unittest
from OLD import TextStripper
from argparse import Namespace
from colorama import Fore, init


speaker_list = [[("Speaker 2", "Larry"), ("Speaker 3", "Josh")]]
extra_speakers = ["Extra 1", "Extra 2", "Extra 3"]
test_main_dir = Path("F:/TESTS")
source_dir = test_main_dir / "SOURCE"
test_in_dir = test_main_dir / "TESTINPUT"
test_out_dir = test_main_dir / "TESTOUTPUT"

def func_name() -> str:
	# f_back looks at the function that called THIS function
	return inspect.currentframe().f_back.f_code.co_name


def reset_files(src: Path, dest: Path):
	if dest.exists():
		shutil.rmtree(dest)
	shutil.copytree(src, dest)


def print_test(name: str, in_path: Path, out_path: Path):
	print(Fore.CYAN + "-----------------------------------------------------")
	print(Fore.CYAN + f"Starting test " + Fore.RED + f"{name}" + Fore.CYAN)
	print(Fore.CYAN + f"Input: {in_path.resolve()}")
	print(Fore.CYAN + f"Output: {out_path.resolve()}")
	print(Fore.CYAN + "-----------------------------------------------------")

suite_name = None

class Tester(unittest.TestCase):

	def setUp(self):
		self.suite_name = suite_name
		return

	@patch('builtins.input')
	def test_single_file(self, mocked_input):
		out_dir = test_out_dir / func_name()
		print_test(func_name(), test_in_dir, out_dir)
		default_args = Namespace(
			path=test_in_dir / "valid_transcript.txt",
			extension=TextStripper.DEFAULT_EXT,
			timecodes=False,
			output=out_dir,
			verbose=True,
			overwrite=False,
			interactive=False,
			recursive=False,
			label=TextStripper.DEFAULT_LABEL,
			extra=list(),
			speakers=speaker_list,
			wildcard=False
		)
		TextStripper.main(default_args)

	@patch('builtins.input')
	def test_dir_no_recursion(self, mocked_input):
		out_dir = test_out_dir / func_name()
		print_test(func_name(), test_in_dir, out_dir)
		default_args = Namespace(
			path=test_in_dir,
			extension=TextStripper.DEFAULT_EXT,
			timecodes=False,
			output=out_dir,
			verbose=True,
			overwrite=False,
			interactive=False,
			recursive=False,
			label=TextStripper.DEFAULT_LABEL,
			extra=list(),
			speakers=speaker_list,
			wildcard=False
		)
		TextStripper.main(default_args)

	@patch('builtins.input')
	def test_dir_overwrite(self, mocked_input):
		out_dir = test_out_dir / func_name()
		print_test(func_name(), test_in_dir, out_dir)
		default_args = Namespace(
			path=test_in_dir,
			extension=TextStripper.DEFAULT_EXT,
			timecodes=False,
			output=out_dir,
			verbose=True,
			overwrite=True,
			interactive=False,
			recursive=False,
			label=TextStripper.DEFAULT_LABEL,
			extra=list(),
			speakers=speaker_list,
			wildcard=False
		)
		TextStripper.main(default_args)
		TextStripper.main(default_args)


	@patch('builtins.input')
	def test_dir_duplicate(self, mocked_input):
		out_dir = test_out_dir / func_name()
		print_test(func_name(), test_in_dir, out_dir)
		default_args = Namespace(
			path=test_in_dir,
			extension=TextStripper.DEFAULT_EXT,
			timecodes=False,
			output=out_dir,
			verbose=True,
			overwrite=False,
			interactive=False,
			recursive=False,
			label=TextStripper.DEFAULT_LABEL,
			 extra=list(),
			speakers=speaker_list,
			wildcard=False
		)
		TextStripper.main(default_args)
		TextStripper.main(default_args)

	@patch('builtins.input')
	def test_dir_relative(self, mocked_input):
		out_dir = test_out_dir / func_name()
		print_test(func_name(), test_in_dir, out_dir)
		default_args = Namespace(
			path=test_in_dir,
			extension=TextStripper.DEFAULT_EXT,
			timecodes=False,
			output="../" + test_main_dir.name + "/" + func_name(),
			verbose=True,
			overwrite=False,
			interactive=False,
			recursive=False,
			label=TextStripper.DEFAULT_LABEL,
			 extra=list(),
			speakers=speaker_list,
			wildcard=False
		)
		TextStripper.main(default_args)

	@patch('builtins.input')
	def test_dir_relative_recursion(self, mocked_input):
		out_dir = test_out_dir / func_name()
		print_test(func_name(), test_in_dir, out_dir)
		default_args = Namespace(
			path=test_in_dir,
			extension=TextStripper.DEFAULT_EXT,
			timecodes=False,
			output="../" + test_main_dir.name + "/" + func_name(),
			verbose=True,
			overwrite=False,
			interactive=False,
			recursive=True,
			label=TextStripper.DEFAULT_LABEL,
			extra=list(),
			speakers=speaker_list,
			wildcard=False
		)
		TextStripper.main(default_args)

	@patch('builtins.input')
	def test_overwrite_single(self, mocked_input):
		out_dir = test_out_dir / func_name()
		print_test(func_name(), test_in_dir, out_dir)
		default_args = Namespace(
			path=test_in_dir / "valid_transcript.txt",
			extension=TextStripper.DEFAULT_EXT,
			timecodes=False,
			output=out_dir,
			verbose=True,
			overwrite=True,
			interactive=False,
			recursive=False,
			label=TextStripper.DEFAULT_LABEL,
			extra=list(),
			speakers=speaker_list,
			wildcard=False
		)
		TextStripper.main(default_args)

	@patch('builtins.input')
	def test_recursion(self, mocked_input):
		out_dir = test_out_dir / func_name()
		print_test(func_name(), test_in_dir, out_dir)
		default_args = Namespace(
			path=test_in_dir,
			extension=TextStripper.DEFAULT_EXT,
			timecodes=False,
			output=out_dir,
			verbose=True,
			overwrite=False,
			interactive=False,
			recursive=True,
			label=TextStripper.DEFAULT_LABEL,
			extra=list(),
			speakers=speaker_list,
			wildcard=False
		)
		TextStripper.main(default_args)

	@patch('builtins.input')
	def test_noverbose(self, mocked_input):
		out_dir = test_out_dir / func_name()
		print_test(func_name(), test_in_dir, out_dir)
		default_args = Namespace(
			path=test_in_dir,
			extension=TextStripper.DEFAULT_EXT,
			timecodes=False,
			output=out_dir,
			verbose=False,
			overwrite=False,
			interactive=False,
			recursive=True,
			label=TextStripper.DEFAULT_LABEL,
			extra=list(),
			speakers=speaker_list,
			wildcard=False
		)
		TextStripper.main(default_args)

	@patch('builtins.input')
	def test_overwrite(self, mocked_input):
		out_dir = test_out_dir / func_name()
		print_test(func_name(), test_in_dir, out_dir)
		default_args = Namespace(
			path=test_in_dir,
			extension=TextStripper.DEFAULT_EXT,
			timecodes=False,
			output="OUTPUT",
			verbose=True,
			overwrite=True,
			interactive=False,
			recursive=True,
			label=TextStripper.DEFAULT_LABEL,
			extra=list(),
			speakers=speaker_list,
			wildcard=False
		)
		TextStripper.main(default_args)

	def test_interactive(self):
		out_dir = test_out_dir / func_name()
		print_test(func_name(), test_in_dir, out_dir)
		default_args = Namespace(
			path=test_in_dir,
			extension=TextStripper.DEFAULT_EXT,
			timecodes=False,
			output=out_dir,
			verbose=True,
			overwrite=False,
			interactive=True,
			recursive=True,
			label=TextStripper.DEFAULT_LABEL,
			extra=list(),
			speakers=speaker_list,
			wildcard=False
		)
		TextStripper.main(default_args)

	@patch('builtins.input')
	def test_wildcard(self, mocked_input):
		out_dir = test_out_dir / func_name()
		print_test(func_name(), test_in_dir, out_dir)
		default_args = Namespace(
			path=test_in_dir / "*",
			extension=TextStripper.DEFAULT_EXT,
			timecodes=False,
			output=out_dir,
			verbose=True,
			overwrite=False,
			interactive=False,
			recursive=True,
			label=TextStripper.DEFAULT_LABEL,
			extra=list(),
			speakers=speaker_list,
			wildcard=True
		)
		TextStripper.main(default_args)

	@patch('builtins.input')
	def test_wildcard_single(self, mocked_input):
		out_dir = test_out_dir / func_name()
		print_test(func_name(), test_in_dir, out_dir)
		default_args = Namespace(
			path=test_in_dir / "valid_*",
			extension=TextStripper.DEFAULT_EXT,
			timecodes=False,
			output=out_dir,
			verbose=True,
			overwrite=False,
			interactive=False,
			recursive=True,
			label=TextStripper.DEFAULT_LABEL,
			 extra=list(),
			speakers=speaker_list,
			wildcard=True
		)
		TextStripper.main(default_args)

	@patch('builtins.input')
	def test_no_speakers(self, mocked_input):
		out_dir = test_out_dir / func_name()
		print_test(func_name(), test_in_dir, out_dir)
		default_args = Namespace(
			path=test_in_dir,
			extension=TextStripper.DEFAULT_EXT,
			timecodes=False,
			output=out_dir,
			verbose=True,
			overwrite=False,
			interactive=False,
			recursive=False,
			label=TextStripper.DEFAULT_LABEL,
			extra=list(),
			speakers=list(),
			wildcard=False
		)
		TextStripper.main(default_args)

	@patch('builtins.input')
	def test_append(self, mocked_input):
		out_dir = test_out_dir / func_name()
		print_test(func_name(), test_in_dir, out_dir)
		default_args = Namespace(
			path=test_in_dir,
			extension=TextStripper.DEFAULT_EXT,
			timecodes=False,
			output=out_dir / "out.txt",
			verbose=True,
			overwrite=False,
			interactive=False,
			recursive=True,
			label=TextStripper.DEFAULT_LABEL,
			speakers=speaker_list,
			wildcard=False,
			extra = True,
		)
		TextStripper.main(default_args)

	@patch('builtins.input')
	def test_extra_speaker(self, mocked_input):
		out_dir = test_out_dir / func_name()
		print_test(func_name(), test_in_dir, out_dir)
		default_args = Namespace(
			path=test_in_dir / "unknown_speaker.txt",
			extension=TextStripper.DEFAULT_EXT,
			timecodes=False,
			output=out_dir,
			verbose=True,
			overwrite=False,
			interactive=False,
			recursive=True,
			label=TextStripper.DEFAULT_LABEL,
			extra=extra_speakers,
			speakers=speaker_list,
			wildcard=False
		)
		TextStripper.main(default_args)



def suite_all_tests():
	global suite_name
	suite_name = func_name()
	test_suite = unittest.TestSuite()
	test_suite.addTest(Tester('test_single_file'))
	test_suite.addTest(Tester('test_dir_no_recursion'))
	test_suite.addTest(Tester('test_dir_overwrite'))
	test_suite.addTest(Tester('test_dir_duplicate'))
	test_suite.addTest(Tester('test_dir_relative'))
	test_suite.addTest(Tester('test_overwrite_single'))
	test_suite.addTest(Tester('test_recursion'))
	test_suite.addTest(Tester('test_noverbose'))
	test_suite.addTest(Tester('test_overwrite'))
	test_suite.addTest(Tester('test_interactive'))
	test_suite.addTest(Tester('test_wildcard'))
	test_suite.addTest(Tester('test_no_speakers'))
	test_suite.addTest(Tester('test_append'))
	test_suite.addTest(Tester('test_extra_speaker'))
	test_suite.addTest(Tester('test_wildcard'))
	test_suite.addTest(Tester('test_wildcard_single'))
	return test_suite

def suite_wildcard():
	global suite_name
	suite_name = func_name()
	test_suite = unittest.TestSuite()
	test_suite.addTest(Tester('test_wildcard'))
	test_suite.addTest(Tester('test_wildcard_single'))
	return test_suite

def suite_single_file():
	global suite_name
	suite_name = func_name()
	test_suite = unittest.TestSuite()
	test_suite.addTest(Tester('test_single_file'))
	test_suite.addTest(Tester('test_wildcard_single'))
	return test_suite

def suite_interactive():
	global suite_name
	suite_name = func_name()
	test_suite = unittest.TestSuite()
	test_suite.addTest(Tester('test_interactive'))
	return test_suite

def suite_failing():
	global suite_name
	suite_name = func_name()
	test_suite = unittest.TestSuite()
	return test_suite

if __name__ == "__main__":
	try:
		shutil.rmtree(test_in_dir, ignore_errors=True)
		shutil.rmtree(test_out_dir, ignore_errors=True)
		shutil.copytree(source_dir, test_in_dir)
		init(autoreset=True)  # Set up colorama text colors

		runner = unittest.TextTestRunner()
		runner.run(suite_all_tests())

		shutil.rmtree(test_in_dir, ignore_errors=True)

	except KeyboardInterrupt:
		exit(1)