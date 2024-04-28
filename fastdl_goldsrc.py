import os
import gzip
from shutil import copyfileobj, copyfile
from sys import argv
from time import time
from argparse import ArgumentParser, RawTextHelpFormatter

gameRootFolder = "./cstrike"
fastdlRootFolder = "./www/fastdl"
blackListPath = "./fastdl_blacklist_goldsrc.txt"
# 1 for fast, 9 for best
CompressionLevel = 6
# Goldsrc doesn't download gzipped files directly. The chromium embedded framework used by steam is also used by the goldsrc engine to download files from fastdl.
# CEF supports Content-Encoding: gzip, maybe we can even use Brotli
# While you can configure your web server to gzip compress on the fly, this is a very bad idea and will burn your CPU.
# Instead you should enable static GZIP on your web server and it will serve the pre-compressed files created by this script.
# If you don't want to use GZIP, set the variable below to False
UseGzipCompression = True

# Goldsrc blacklist needs a full rework.
# Since there are no VPks, default models, sounds, etc are stored in the game folder.
# For Goldsrc, we should blacklist the full path to the file. Example: 'models/barney.mdl' instead of just 'barney.mdl'

gameFolders = [
	("maps", [".bsp", ".nav", ".txt", ".cfg", ".res", ".gmr", ".gsr"]),
	("gfx", [".tga", ".bmp"]),
	("overviews", [".bmp", ".tga", ".txt"]),
	("models", [".mdl", ".bmp"]),
	("sprites", [".spr"]),
	("sound", [".mp3", ".wav", ".ogg"]),
	("", [".wad"])
]

ETCconstant = 9.5e-08
TotalFilesUpdated = 0
TotalFilesChanged = 0
TotalFilesRemoved = 0
cmpReadSize = 128000
ProcessArgs = None


def printVerbose(level, *args, **kwargs):
	if ProcessArgs.verbose_level >= level: 
		print(*args, **kwargs)

def gzipCompressFile(rootfile, fdfile):
	printVerbose(2, "Compressing {}, ETC: {:.2f} seconds...".format(rootfile, os.path.getsize(rootfile) * ETCconstant))
	with open(rootfile, "rb") as inp, gzip.open(fdfile, "wb", CompressionLevel) as out:
		out.writelines(inp)
		copyfileobj(inp, out)

def filesEqual(rootfile, fdfile, gzformat = False):
	prevtime = time()
	if gzformat:
		with open(rootfile, "rb") as inp,  gzip.open(fdfile, "rb") as out:
			while True:
				p1 = inp.read(cmpReadSize)
				p2 = out.read(cmpReadSize)
				if p1 != p2:
					printVerbose(2, "GZ File {} compared in {:.2f} seconds".format(rootfile, time() - prevtime))
					return False
				if not p1:
					printVerbose(2, "GZ File {} compared in {:.2f} seconds".format(rootfile, time() - prevtime))
					return True
	else:
		with open(rootfile, "rb") as inp, open(fdfile, "rb") as out:
			while True:
				p1 = inp.read(cmpReadSize)
				p2 = out.read(cmpReadSize)
				if p1 != p2:
					printVerbose(2, "File {} compared in {:.2f} seconds".format(rootfile, time() - prevtime))
					return False
				if not p1:
					printVerbose(2, "File {} compared in {:.2f} seconds".format(rootfile, time() - prevtime))
					return True

def initBlacklist(path_to_blacklist):
	files = None
	if not os.path.exists(path_to_blacklist):
		printVerbose(1, "BlackList not found at {}. ignoring...".format(path_to_blacklist))
	else:
		printVerbose(1, "BlackList found at {}. Parsing files...".format(path_to_blacklist))
		with open(path_to_blacklist, "r") as inp:
			lines = inp.readlines()
			files = []
			for line in lines:
				stripped_line = line.strip()
				if len(stripped_line) != 0 and stripped_line[0] != '#' and not stripped_line.startswith('//'):
					files.append(stripped_line)
	return files

def addToFastdl(rootfile, fdfile, copy = False):
	global TotalFilesUpdated, TotalFilesChanged, TotalFilesRemoved
	
	if not os.path.exists(fdfile):
		TotalFilesUpdated += 1
		printVerbose(0, "Adding {} to fastdl...".format(rootfile))
		if copy:
			copyfile(rootfile, fdfile)
		else:
			gzipCompressFile(rootfile, fdfile)
	elif ProcessArgs.full_check:
		if copy:
			if os.path.getsize(fdfile) != os.path.getsize(rootfile) or not filesEqual(rootfile, fdfile):
				TotalFilesChanged += 1
				printVerbose(0, "Found changed file {}, replacing...".format(rootfile))
				copyfile(rootfile, fdfile)
		else:
			if not filesEqual(rootfile, fdfile, True):
				TotalFilesChanged += 1
				printVerbose(0, "Found changed file {}, replacing...".format(rootfile))
				gzipCompressFile(rootfile, fdfile)

def main():
	global TotalFilesUpdated, TotalFilesChanged, TotalFilesRemoved

	if not os.path.exists(gameRootFolder):
		print("Game root \"{}\" folder wasn't found!".format(gameRootFolder))
		return
	if not os.path.exists(fastdlRootFolder):
		print("Fastdl \"{}\" folder wasn't found!".format(fastdlRootFolder))
		return
	
	BlackListedFiles = initBlacklist(blackListPath)
	timestart = time()
	
	try:
		for expfolder, exts in gameFolders:
			for dirpath, dirnames, filenames in os.walk(os.path.join(gameRootFolder, expfolder)):
				for file in filenames:
					if os.path.splitext(file)[1] in exts:
						#ignore blacklisted files
						if BlackListedFiles is not None and file in BlackListedFiles:
							printVerbose(2, "Found {} which is blacklisted, ignoring...".format(file))
							continue
						
						fulldir = os.path.join(fastdlRootFolder, os.path.relpath(dirpath, gameRootFolder))
						if not os.path.exists(fulldir):
							printVerbose(0, "Directory {} wasn't found on fastdl path, creating...".format(fulldir))
							os.makedirs(fulldir)
						rootfile = os.path.join(dirpath, file)
						
						# Goldsrc doesn't have the 150 MB limit on compressed files
						if gzipCompressFile:
							addToFastdl(rootfile, os.path.join(fulldir, "{}.gz".format(file)))
						else:
							addToFastdl(rootfile, os.path.join(fulldir, file), True)

			for dirpath, dirnames, filenames in os.walk(os.path.join(fastdlRootFolder, expfolder)):
				for file in filenames:
					if os.path.splitext(file)[1] == ".gz":
						filename = os.path.splitext(file)[0]
					else:
						filename = file

					if not os.path.exists(os.path.join(gameRootFolder, os.path.relpath(dirpath, fastdlRootFolder), filename)):
						TotalFilesRemoved += 1
						printVerbose(0, "Found removed file {}, deleting...".format(os.path.join(gameRootFolder, os.path.relpath(dirpath, fastdlRootFolder), filename)))
						os.remove(os.path.join(dirpath, file))

			for dirpath, dirnames, filenames in os.walk(os.path.join(fastdlRootFolder, expfolder), topdown = False):
				if not os.listdir(dirpath):
					printVerbose(0, "Found empty directory {} on fastdl, removing...".format(dirpath))
					os.rmdir(dirpath)
	except Exception as e:
		print(e)

	printVerbose(1, "Fastdl was updated successfully. (Took {:.2f} seconds to complete)".format(time() - timestart))
	printVerbose(1, "Was added {} entries.".format(TotalFilesUpdated))
	printVerbose(1, "Was changed {} entries.".format(TotalFilesChanged))
	printVerbose(1, "Was removed {} entries.".format(TotalFilesRemoved))


if __name__ == "__main__":
	parser = ArgumentParser(description = 'Traverses specified folders and compresses files on a Source FastDL manner.', formatter_class=RawTextHelpFormatter)
	parser.add_argument('-f', '--full_check',
			help = 'Performs full check on all files to ensure their validity (NOTE: The operation is very costly!!!)',
			action = 'store_true', default = False, dest = 'full_check')
	parser.add_argument('-v', '--verbose',
			help = 'Verbosity levels (default: 2):\n0 - Only changes to the data would be printed;\n'
				'1 - Header, footer, and data changes would be printed;\n'
				'2 - Header, footer, blacklist notifications, comparison info (if -f is used) and data changes would be printed;',
			action = 'store', type = int, choices = range(0, 3), default = 2, dest = 'verbose_level')
	
	ProcessArgs = parser.parse_args()

	main()
