import ctypes as C
from ctypes import cdll
import sys
import source.utils as utils
from skimage.filters import gaussian
from skimage.restoration import denoise_bilateral
import numpy as np

try:
	if sys.platform == "linux" or sys.platform == "linux2":
		lib = cdll.LoadLibrary('coraline/libcoraline.so')
	elif sys.platform == "win32":
		lib = cdll.LoadLibrary('coraline/coraline.dll')

except:
	lib = None

#import numpy as np

def segment(img, mask, l = 0, conservative = 0.1, grow = 0, radius = 30):
	if lib is None:
		raise Exception("Coraline library (libcoraline.so, coraline.dll) not found.")

	img = gaussian(img, sigma = 1.5, multichannel=False)
	img = img*255;
	img = img.astype(np.uint8)
	qimg = utils.rgbToQImage(img)
	qimg.save("Smoothed.jpg")

	w = img.shape[1]
	h = img.shape[0]
	W = mask.shape[1]
	H = mask.shape[0]
	if (w != W) or (h != H):
		print(w, h, W, H)
		exit(0)

	#print(C.c_float(l), l)
	lib.Coraline_segment(C.c_void_p(img.ctypes.data), C.c_void_p(mask.ctypes.data), C.c_int(w), C.c_int(h),
						 C.c_float(l), C.c_float(conservative), C.c_float(grow), C.c_float(radius))

#
# class Coraline(object):
# 	def __init__(self, img, mask):
# 		if lib is None:
# 			raise Exception("Coraline library (libcoraline.so, coraline.dll) not found.")
# 		w = img.shape[1]
# 		h = img.shape[0]
# 		W = mask.shape[1]
# 		H = mask.shape[0]
# 		if (w != W) or (h != H):
# 			print(w, h, W, H)
# 			exit(0)
#
# 		handle = lib.Coraline_new(C.c_void_p(img.ctypes.data), C.c_void_p(mask.ctypes.data), C.c_int(w), C.c_int(h))
# 		self.obj = C.c_void_p(handle)
#
# 		print("CORALINE PY")
# 		print(self.obj)
# 		print(self)
#
# 	def __del__(self):
# 		lib.Coraline_delete(self.obj)
#
# 	def setImg(self, img):
# 		w = C.c_int(img.shape[1])
# 		h = C.c_int(img.shape[0])
# 		lib.Coraline_setImg(self.obj, C.c_void_p(img.ctypes.data), w, h)
#
# 	def setMask(self, mask):
# 		w = C.c_int(mask.shape[1])
# 		h = C.c_int(mask.shape[0])
# 		lib.Coraline_setMask(self.obj, C.c_void_p(mask.ctypes.data), w, h)
#
# 	def setPred(self, pred):
# 		w = C.c_int(pred.shape[1])
# 		h = C.c_int(pred.shape[0])
# 		lib.Coraline_setPred(self.obj, C.c_void_p(pred.ctypes.data), w, h)
#
# 	def setLambda(self, l):
# 		lib.Coraline_setLambda(self.obj, C.c_float(l))
#
# 	def setConservative(self, conservative):
# 		print(self.obj)
# 		lib.Coraline_setConservative(self.obj, C.c_float(conservative))
#
# 	def segment(self):
# 		w = 100
# 		h = 100
# 		data = lib.Coraline_segment(self.obj)
# 		data = C.cast(data, C.POINTER(C.c_ubyte))
# 		mask = np.ctypeslib.as_array(data, shape=(w, h))
# 		return mask
#



#mask = np.zeros((100,100))
#image =  np.zeros((100, 100))
#coraline = Coraline(image, mask)
#mask = coraline.segment()
#print(mask)
