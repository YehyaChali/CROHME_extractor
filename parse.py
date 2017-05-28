import sys
import os

import xml.etree.ElementTree as ET

import numpy as np

from skimage.draw import line

import pickle

data_dir = 'data'
crohme_package = os.path.join(data_dir, 'CROHME_full_v2')


outputs_rel_path = 'outputs'
train_dir = os.path.join(outputs_rel_path, 'train')
test_dir = os.path.join(outputs_rel_path, 'test')
validation_dir = os.path.join(outputs_rel_path, 'validation')




def get_traces_data(inkml_file_abs_path):

	traces_data = []

	tree = ET.parse(inkml_file_abs_path)
	root = tree.getroot()
	doc_namespace = "{http://www.w3.org/2003/InkML}"

	'Stores traces_all with their corresponding id'
	traces_all = [{'id': trace_tag.get('id'), 
						'coords': [[round(float(axis_coord)) if float(axis_coord).is_integer() else round(float(axis_coord) * 10000) \
										for axis_coord in coord[1:].split(' ')] if coord.startswith(' ') \
									else [round(float(axis_coord)) if float(axis_coord).is_integer() else round(float(axis_coord) * 10000) \
										for axis_coord in coord.split(' ')] \
								for coord in (trace_tag.text).replace('\n', '').split(',')]} \
								for trace_tag in root.findall(doc_namespace + 'trace')]

	'Sort traces_all list by id to make searching for references faster'
	traces_all.sort(key=lambda trace_dict: int(trace_dict['id']))


	'Always 1st traceGroup is a redundant wrapper'
	traceGroupWrapper = root.find(doc_namespace + 'traceGroup')

	if traceGroupWrapper is not None:
		for traceGroup in traceGroupWrapper.findall(doc_namespace + 'traceGroup'):

			label = traceGroup.find(doc_namespace + 'annotation').text
			
			'traces of the current traceGroup'
			traces_curr = []
			for traceView in traceGroup.findall(doc_namespace + 'traceView'):

				'Id reference to specific trace tag corresponding to currently considered label'
				traceDataRef = int(traceView.get('traceDataRef'))

				'Each trace is represented by a list of coordinates to connect'
				single_trace = traces_all[traceDataRef]['coords']
				traces_curr.append(single_trace)


			traces_data.append({'label': label, 'trace_group': traces_curr})

	else:
		'Consider Validation data that has no labels'
		[traces_data.append({'trace_group': [trace['coords']]}) for trace in traces_all]

	return traces_data

def parse_inkmls(data_dir_abs_path):
	'Accumulates traces_data of all the inkml files\
	located in the specified directory'
	patterns_enc = []
	classes_rejected = []

	'Check object is a directory'
	if os.path.isdir(data_dir_abs_path):

		for inkml_file in os.listdir(data_dir_abs_path):

			if inkml_file.endswith('.inkml'):
				inkml_file_abs_path = os.path.join(data_dir_abs_path, inkml_file)

				print('Parsing:', inkml_file_abs_path, '...')


				' **** Each entry in traces_data represent SEPARATE pattern\
					which might(NOT) have its label encoded along with traces that it\'s made up of **** '
				traces_data_curr_inkml = get_traces_data(inkml_file_abs_path)

				'Each entry in patterns_enc is a dictionary consisting of \
				pattern_drawn matrix and its label'
				ptrns_enc_inkml_curr, classes_rej_inkml_curr = convert_to_imgs(traces_data_curr_inkml, box_axis_size=box_axis_size)
				patterns_enc += ptrns_enc_inkml_curr
				classes_rejected += classes_rej_inkml_curr


	return patterns_enc, classes_rejected

def get_min_coords(trace_group):
	min_x_coords = []
	min_y_coords = []
	max_x_coords = []
	max_y_coords = []

	for trace in trace_group:

		x_coords = [coord[0] for coord in trace]
		y_coords = [coord[1] for coord in trace]

		min_x_coords.append(min(x_coords))
		min_y_coords.append(min(y_coords))
		max_x_coords.append(max(x_coords))
		max_y_coords.append(max(y_coords))

	return min(min_x_coords), min(min_y_coords), max(max_x_coords), max(max_y_coords)

'shift pattern to its relative position'
def shift_trace_grp(trace_group, min_x, min_y):
	shifted_trace_grp = []

	for trace in trace_group:
		shifted_trace = [[coord[0] - min_x, coord[1] - min_y] for coord in trace]

		shifted_trace_grp.append(shifted_trace)

	return shifted_trace_grp

'Interpolates a pattern so that it fits into a box with specified size'
def interpolate(trace_group, trace_grp_height, trace_grp_width, box_axis_size):
	interpolated_trace_grp = []

	if trace_grp_height == 0:
		trace_grp_height += 1
	if trace_grp_width == 0:
		trace_grp_width += 1

	'' 'KEEP original size ratio' ''
	trace_grp_ratio = (trace_grp_width) / (trace_grp_height)

	box_ratio = box_axis_size / box_axis_size


	scale_factor = 1.0
	'' 'Set \"rescale coefficient\" magnitude' ''
	if trace_grp_ratio < box_ratio:

		scale_factor = (box_axis_size / trace_grp_height)
	else:

		scale_factor = (box_axis_size / trace_grp_width)



	for trace in trace_group:
		'coordintes convertion to int type necessary'
		interpolated_trace = [[round(coord[0] * scale_factor), round(coord[1] * scale_factor)] for coord in trace]

		interpolated_trace_grp.append(interpolated_trace)

	return interpolated_trace_grp

def center_pattern(trace_group, max_x, max_y, box_axis_size):

	x_margin = int((box_axis_size - max_x) / 2)
	y_margin = int((box_axis_size - max_y) / 2)

	return shift_trace_grp(trace_group, min_x= -x_margin, min_y= -y_margin)

def draw_pattern(trace_group, box_axis_size):

	pattern_drawn = np.ones(shape=(box_axis_size, box_axis_size), dtype=np.float32)
	for trace in trace_group:

		' SINGLE POINT TO DRAW '
		if len(trace) == 1:
			x_coord = trace[0][0]
			y_coord = trace[0][1]
			pattern_drawn[y_coord, x_coord] = 0.0

		else:
			' TRACE HAS MORE THAN 1 POINT '

			'Iterate through list of traces endpoints'
			for pt_idx in range(len(trace) - 1):

				'Indices of pixels that belong to the line. May be used to directly index into an array'
				pattern_drawn[line(r0=trace[pt_idx][1], c0=trace[pt_idx][0], 
								   r1=trace[pt_idx + 1][1], c1=trace[pt_idx + 1][0])] = 0.0


	return pattern_drawn

def convert_to_imgs(traces_data, box_axis_size):
	patterns_enc = []
	classes_rejected = []

	for pattern in traces_data:

		trace_group = pattern['trace_group']

		'mid coords needed to shift the pattern'
		min_x, min_y, max_x, max_y = get_min_coords(trace_group)

		'traceGroup dimensions'
		trace_grp_height, trace_grp_width = max_y - min_y, max_x - min_x



		'shift pattern to its relative position'
		shifted_trace_grp = shift_trace_grp(trace_group, min_x=min_x, min_y=min_y)



		'Interpolates a pattern so that it fits into a box with specified size'
		'method: LINEAR INTERPOLATION'
		try:
			interpolated_trace_grp = interpolate(shifted_trace_grp, \
												 trace_grp_height=trace_grp_height, trace_grp_width=trace_grp_width, box_axis_size=box_axis_size-1)
		except Exception as e:
			print(e)
			print('This data is corrupted - skipping.')
			classes_rejected.append(pattern.get('label'))

			continue



		'Get min, max coords once again in order to center scaled patter inside the box'
		min_x, min_y, max_x, max_y = get_min_coords(interpolated_trace_grp)


		centered_trace_grp = center_pattern(interpolated_trace_grp, max_x=max_x, max_y=max_y, box_axis_size=box_axis_size)

		'Center scaled pattern so it fits a box with specified size'
		pattern_drawn = draw_pattern(centered_trace_grp, box_axis_size=box_axis_size)
		# plt.imshow(pattern_drawn, cmap='gray')
		# plt.show()

		pattern_enc = dict({'pattern': pattern_drawn, 'label': pattern.get('label')})


		patterns_enc.append(pattern_enc)



	return patterns_enc, classes_rejected

if __name__ == '__main__':

	print(' Script flags:', '<box_axis_size>', '<dataset_ver=2012>')


	'parse 1st arg'
	if len(sys.argv) < 2:
		print('\n + Usage:', sys.argv[0], '<box_axis_size>', '<dataset_ver=2012>')
		exit()

	try:
		box_axis_size = int(sys.argv[1])
	except Exception as e:
		print(e)
		exit()

	dataset_ver = '2012'
	if len(sys.argv) >= 3:

		if sys.argv[2].isdigit():
			dataset_ver = sys.argv[2]
		else:
			print('Version of the dataset has to be a number - CROHME comp. year(e.g. \'2013\').')
			exit()

	ver_found = False
	for crohme_comp_ver in os.listdir(crohme_package):

		crohme_comp_ver_abs = os.path.join(crohme_package, crohme_comp_ver)

		if os.path.isdir(crohme_comp_ver_abs):

			if crohme_comp_ver.endswith(dataset_ver + '_data'):

				data_abs_path = crohme_comp_ver_abs
				ver_found = True

	if ver_found is False:
		print(' # Specified CROHME dataset version was NOT FOUND.')
		exit()

	print(' ! Warning:', 'Loading data from', data_abs_path)




	'Make dirs if needed'
	if not os.path.exists(outputs_rel_path):
		os.mkdir(outputs_rel_path)
	# outputs_abs_path, box_axis_size = parse_cmd_args(outputs_rel_path)




	' **** Names of directories containing TRAIN, TEST \
	vary depending of the package\'s version picked **** '
	if dataset_ver == '2012':

		train_data = os.path.join(data_abs_path, 'trainData')
		test_set_dir = os.path.join(data_abs_path, 'testDataGT')
		validation_set_dir = os.path.join(data_abs_path, 'testData')

		train_patterns_enc, classes_rejected = parse_inkmls(train_data)

		for class_rejected in set(classes_rejected):
			print(classes_rejected.count(class_rejected), 'rected entries of:\'', class_rejected, '\' class.')




	elif dataset_ver == '2013':

		train_data = os.path.join(data_abs_path, 'TrainINKML')
		test_set_dir = os.path.join(data_abs_path, 'TestINKMLGT')
		validation_set_dir = os.path.join(data_abs_path, 'TestINKML')


		'Parse TRAIN SET'
		train_patterns_enc = []
		classes_rejected = []
		for mini_train_set in os.listdir(train_data):
			mini_train_set_abs_path = os.path.join(train_data, mini_train_set)

			ptrns_enc_curr_set, classes_rej_curr_set = parse_inkmls(mini_train_set_abs_path)
			train_patterns_enc += ptrns_enc_curr_set
			classes_rejected += classes_rej_curr_set

		for class_rejected in set(classes_rejected):
			print(classes_rejected.count(class_rejected), 'rected entries of:\'', class_rejected, '\' class.')

	# for pattern in train_patterns_enc:
	# 	print('label:', pattern['label'])
	# 	plt.imshow(pattern['pattern'], cmap='gray')
	# 	plt.show()


	test_patterns_enc, test_classes_rej = parse_inkmls(test_set_dir)
	[print(test_classes_rej.count(class_rejected), 'rected entries of:\'', class_rejected, '\' class.') for class_rejected in set(test_classes_rej)]


	valid_patterns_enc, valid_classes_rej = parse_inkmls(validation_set_dir)
	print(len(valid_classes_rej), 'validation set entries were REJECTED.')




	'PRINT LABELS extracted'
	labels_extracted = set([pattern['label'] for pattern in (train_patterns_enc + test_patterns_enc)])
	print(len(labels_extracted), 'LABELS were extracted:\n')
	[print(' ', label_extr) for label_extr in labels_extracted]



	print('\nTRAING SET SIZE:', len(train_patterns_enc))
	print('TEST SET SIZE:', len(test_patterns_enc))
	print('VALIDATION SET SIZE:', len(valid_patterns_enc))

	' DUMP DATA '
	print('\nDumping extracted data ...')
	'Make dirs if needed'
	if not os.path.exists(train_dir):
		os.mkdir(train_dir)
	if not os.path.exists(test_dir):
		os.mkdir(test_dir)
	if not os.path.exists(validation_dir):
		os.mkdir(validation_dir)


	with open(os.path.join(train_dir, 'train.pickle'), 'wb') as train:
		pickle.dump(train_patterns_enc, train, protocol=pickle.HIGHEST_PROTOCOL)
		print('Data has been successfully dumped into', train.name)

	with open(os.path.join(test_dir, 'test.pickle'), 'wb') as test:
		pickle.dump(test_patterns_enc, test, protocol=pickle.HIGHEST_PROTOCOL)
		print('Data has been successfully dumped into', test.name)

	with open(os.path.join(validation_dir, 'validation.pickle'), 'wb') as validation:
		pickle.dump(valid_patterns_enc, validation, protocol=pickle.HIGHEST_PROTOCOL)
		print('Data has been successfully dumped into', validation.name)