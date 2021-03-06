# TagLab                                               
# A semi-automatic segmentation tool                                    
#
# Copyright(C) 2019                                         
# Visual Computing Lab                                           
# ISTI - Italian National Research Council                              
# All rights reserved.                                                      
                                                                          
# This program is free software; you can redistribute it and/or modify      
# it under the terms of the GNU General Public License as published by      
# the Free Software Foundation; either version 2 of the License, or         
# (at your option) any later version.                                       
                                                                           
# This program is distributed in the hope that it will be useful,           
# but WITHOUT ANY WARRANTY; without even the implied warranty of            
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the             
#GNU General Public License (http://www.gnu.org/licenses/gpl.txt)          
# for more details.                                               

import os
import shutil
import numpy as np
from cv2 import fillPoly

from skimage import measure

from skimage.filters import sobel
from scipy import ndimage as ndi
from PyQt5.QtGui import QPainter, QImage, QPen, QBrush, QColor, qRgb
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtCore import Qt
from skimage.color import rgb2gray
from skimage.draw import polygon_perimeter

from source import utils

import pandas as pd
from scipy import ndimage as ndi
from skimage.morphology import watershed, flood
from skimage.filters import gaussian
from source.Blob import Blob
import source.Mask as Mask



class Group(object):

    def __init__(self, blobs, id):

        # list of the blobs that form this group
        self.blobs = []
        for blob in blobs:
            self.blobs.append(blob)

        for blob in blobs:

            blob.group = self

        # centroid of the group
        sumx = 0.0
        sumy = 0.0
        n = 0
        for blob in self.blobs:
            blob_mask = blob.getMask()
            for y in range(blob_mask.shape[0]):
                for x in range(blob_mask.shape[1]):
                    if blob_mask[y, x] == 1:
                        sumx += float(x + blob.bbox[1])
                        sumy += float(y + blob.bbox[0])
                        n += 1

        cx = sumx / n
        cy = sumy / n

        self.centroid = np.zeros((2))
        self.centroid[0] = cx
        self.centroid[1] = cy

        # update instance name for each blob
        for blob in self.blobs:
            blob.instace_name = "coral-group-" + str(id)


class Annotation(object):
    """
        Annotation object contains all the annotations as a list of blobs.
    """

    def __init__(self, labels_info):

        # list of all blobs
        self.seg_blobs = []

        # annotations coming from previous years (for comparison, no editing is possible)
        self.prev_blobs = []

        # list of all groups
        self.groups = []

        # labels info
        self.labels_info = labels_info

        # progressive id of the blobs
        self.progressive_id = 0

    def addGroup(self, blobs):

        id = len(self.groups)
        group = Group(blobs, id+1)
        self.groups.append(group)
        return group

    def addBlob(self, blob):
        self.seg_blobs.append(blob)

    def removeBlob(self, blob):
        index = self.seg_blobs.index(blob)
        del self.seg_blobs[index]


    def blobsFromMask(self, seg_mask, map_pos_x, map_pos_y, area_mask):
        # create the blobs from the segmentation mask

        last_blobs_added = []

        seg_mask = ndi.binary_fill_holes(seg_mask).astype(int)
        label_image = measure.label(seg_mask)

        area_th = area_mask * 0.2

        for region in measure.regionprops(label_image):

            if region.area > area_th:

                blob = Blob(region, map_pos_x, map_pos_y, self.progressive_id)
                self.progressive_id += 1

                last_blobs_added.append(blob)

        return last_blobs_added

    def removeGroup(self, group):

        # the blobs no more belong to this group
        for blob in group.blobs:
            blob.group = None
            blob.instace_name = "coral" + str(blob.id)

        # remove from the list of the groups
        index = self.groups.index(group)
        del self.groups[index]




    def as_dict(self, i):

        blob = self.seg_blobs[i]
        return {'coral name': blob.blob_name, 'group name': blob.group, 'class name': blob.class_name, ' centroid ': blob.centroid, 'coral area': blob.area, 'coral perimeter': blob.perimeter}

    def union(self, blobs):
        """
        Create a new blob that is the union of the (two) blobs given
        """
        #boxs are in image space, masks invert x and y.
        boxes = []
        for blob in blobs:
            boxes.append(blob.bbox)
        box = Mask.jointBox(boxes)
        (mask, box) = Mask.jointMask(box, box)

        for blob in blobs:
            Mask.paintMask(mask, box, blob.getMask(), blob.bbox, 1)

        if mask.any():
            # measure is brutally slower with non int types (factor 4), while byte&bool would be faster by 25%, conversion is fast.
            blob = blobs[0].copy()
            blob.updateUsingMask(box, mask.astype(int))

            return blob
        return None


    def subtract(self, blobA, blobB, scene):
        """
        Create a new blob that subtracting the second blob from the first one
        """

        (mask, box) = Mask.subtract(blobA.getMask(), blobA.bbox, blobB.getMask(), blobB.bbox)
        if mask.any():
            # measure is brutally slower with non int types (factor 4), while byte&bool would be faster by 25%, conversion is fast.
            blobA.updateUsingMask(box, mask.astype(int))
            return True
        return False



    def cut(self, blob, lines):
        """
        Given a curve specified as a set of points and a selected blob, the operation cuts it in several separed new blobs
        """
        points = blob.lineToPoints(lines, snap=False)

        mask = blob.getMask()
        original = mask.copy()
        box = blob.bbox
        #box is y, x, w, h
        Mask.paintPoints(mask, box, points, 0)

        label_image = measure.label(mask, connectivity=1)
        for point in points:
            x = point[0] - box[1]
            y = point[1] - box[0]

            if x <= 0 or y <= 0 or x >= box[2] -1 or y >= box[3] -1:
                continue

            if original[y][x] == 0:
                continue
            largest = 0
            largest = max(label_image[y+1][x], largest)
            largest = max(label_image[y-1][x], largest)
            largest = max(label_image[y][x+1], largest)
            largest = max(label_image[y][x-1], largest)
            label_image[y][x] = largest

        area_th = 30
        created_blobs = []
        first = True
        for region in measure.regionprops(label_image):

            if region.area > area_th:
                b = Blob(region, box[1], box[0], self.progressive_id)
                self.progressive_id += 1
                b.class_color = blob.class_color
                b.class_name = blob.class_name
                created_blobs.append(b)

        return created_blobs
    #expect numpu img and mask
    def refineBorder(self, box, blob, img, mask, grow):
        try:
            from coraline.Coraline import segment
            segment(img, mask, 0.0, conservative=0.07, grow=grow, radius=30)

        except Exception as e:
            msgBox = QMessageBox()
            msgBox.setText(str(e))
            msgBox.exec()
            return

        #TODO this should be moved to a function!
        area_th = 30
        created_blobs = []
        first = True
        label_image = measure.label(mask, connectivity=1)
        for region in measure.regionprops(label_image):
            if region.area > area_th:
                b = Blob(region, box[1], box[0], self.progressive_id)
                self.progressive_id += 1
                b.class_color = blob.class_color
                b.class_name = blob.class_name
                created_blobs.append(b)

        return created_blobs

    def splitBlob(self,map, blob, seeds):

        seeds = np.asarray(seeds)
        seeds = seeds.astype(int)
        mask = blob.getMask()
        box = blob.bbox
        cropimg = utils.cropQImage(map, box)
        cropimgnp = rgb2gray(utils.qimageToNumpyArray(cropimg))

        edges = sobel(cropimgnp)

        # x,y
        seeds_matrix = np.zeros_like(mask)

        size = 40
        #
        for i in range(0, seeds.shape[0]):
        #y,x
            seeds_matrix[seeds[i, 1] - box[0] - (size - 1): seeds[i, 1] - box[0] + (size - 1),
            seeds[i, 0] - box[1] - (size - 1): seeds[i, 0] - box[1] + (size - 1)] = 1

        distance = ndi.distance_transform_edt(mask)
        # distance = ndi.distance_transform_edt(cropimg)
        seeds_matrix = seeds_matrix > 0.5
        markers = ndi.label(seeds_matrix)[0]
        # labels = watershed(-distance, markers, mask=mask)
        labels = watershed((-distance+100*edges)/2, markers, mask=mask)
        created_blobs = []
        for region in measure.regionprops(labels):
                b = Blob(region, box[1], box[0], self.progressive_id)
                self.progressive_id += 1
                b.class_color = blob.class_color
                b.class_name = blob.class_name
                created_blobs.append(b)

        return created_blobs


    def createCrack(self, blob, input_arr, x, y, tolerance, preview=True):

        """
        Given a inner blob point (x,y), the function use it as a seed for a paint butcket tool and create
        a correspondent blob hole
        """


        box = blob.bbox
        x_crop = x - box[1]
        y_crop = y - box[0]

        input_arr = gaussian(input_arr, 2)
        # input_arr = segmentation.inverse_gaussian_gradient(input_arr, alpha=1, sigma=1)

        blob_mask = blob.getMask()

        crack_mask = flood(input_arr, (int(y_crop), int(x_crop)), tolerance=tolerance).astype(int)
        cracked_blob = np.logical_and((blob_mask > 0), (crack_mask < 1))
        cracked_blob = cracked_blob.astype(int)

        if preview:
            return cracked_blob

        regions = measure.regionprops(measure.label(cracked_blob))

        area_th = 1000
        created_blobs = []

        for region in regions:
            if region.area > area_th:
                id = len(self.seg_blobs)
                b = Blob(region, box[1], box[0], self.progressive_id)
                self.progressive_id += 1
                b.class_color = blob.class_color
                b.class_name = blob.class_name
                created_blobs.append(b)

        return created_blobs

            # if len(regions):
            #     largest = regions[0]
            #     for region in regions:
            #         if region.area > largest.area and region.area > 1000:
            #             largest = region
            #
            #
            #     # adjust the image bounding box (relative to the region mask) to directly use area.image mask
            #     # image box is standard (minx, miny, maxx, maxy)
            #     box = np.array([box[0] + largest.bbox[0], box[1] + largest.bbox[1], largest.bbox[3], largest.bbox[2]])
            #     try:
            #         self.updateUsingMask(box, largest.image.astype(int))
            #     except:
            #         pass

            #self.updateUsingMask(self.bbox, cracked_blob)

    def editBorder(self, blob, lines):
        points = [blob.drawLine(line) for line in lines]

        if points is None or len(points) == 0:
            return

        # compute the box for the outer contour
        (mask, box) = self.editBorderContour(blob, blob.contour, points)

        for contour in blob.inner_contours:
            (inner_mask, inner_box) = self.editBorderContour(blob, contour, points)
            Mask.paintMask(mask, box, inner_mask, inner_box, 0)

        blob.updateUsingMask(box, mask)
        return

    def editBorderContour(self, blob, contour, points):
        snapped_points = np.empty(shape=(0, 2), dtype=int)
        for arc in points:
            snapped = blob.snapToContour(arc, contour)
            if snapped is not None:
                snapped_points = np.append(snapped_points, snapped, axis = 0)

        contour_box = Mask.pointsBox(contour, 4)

        if snapped_points is None or len(snapped_points) == 0:
            # not very elegant repeated code...
            (mask, box) = Mask.jointMask(contour_box, contour_box)
            origin = np.array([box[1], box[0]])
            contour_points = contour.round().astype(int)
            fillPoly(mask, pts=[contour_points - origin], color=(1))
            return (mask, box)

        points_box = Mask.pointsBox(snapped_points, 4)

        # create a mask large enough to accomodate the points and the contour and paint.
        (mask, box) = Mask.jointMask(contour_box, points_box)

        origin = np.array([box[1], box[0]])
        contour_points = contour.round().astype(int)
        fillPoly(mask, pts=[contour_points - origin], color=(1, 1, 1))

        Mask.paintPoints(mask, box, snapped_points, 1)

        mask = ndi.binary_fill_holes(mask)

        # now draw in black the part of the points inside the contour
        Mask.paintPoints(mask, box, snapped_points, 0)

        # now we label all the parts and keep the larges only
        regions = measure.regionprops(measure.label(mask, connectivity=1))

        largest = max(regions, key=lambda region: region.area)

        # adjust the image bounding box (relative to the region mask) to directly use area.image mask
        box = np.array([box[0] + largest.bbox[0], box[1] + largest.bbox[1], largest.bbox[3] - largest.bbox[1],
                        largest.bbox[2] - largest.bbox[0]])
        return (largest.image, box)

    def statistics(self):
        """
        Print some statistics about the current annotations.
        """

        number_of_seg = len(self.seg_blobs)
        dimensions = np.zeros(number_of_seg)
        for i, blob in enumerate(self.seg_blobs):

            dimensions[i] = blob.size()

        print("-------------------------")
        print("Total seg. blobs : %d" % number_of_seg)
        print("Minimum size     : %d" % np.min(dimensions))
        print("Maximum size     : %d" % np.max(dimensions))
        print("Size deviation   : %f" % np.std(dimensions))
        print("-------------------------")

    def clickedBlob(self, x, y):
        """
        It returns the blob clicked with the smallest area (to avoid problems with overlapping blobs).
        """

        blobs_clicked = []

        for blob in self.seg_blobs:

            point = np.array([[x, y]])
            out = measure.points_in_poly(point, blob.contour)
            if out[0] == True:
                blobs_clicked.append(blob)

        area_min = 100000000.0
        selected_blob = None
        for i in range(len(blobs_clicked)):
            blob = blobs_clicked[i]
            if blob.area < area_min:
                area_min = blob.area
                selected_blob = blob

        return selected_blob





    ###########################################################################
    ### IMPORT / EXPORT

    def import_label_map(self, filename, reference_map):
        """
        It imports a label map and create the corresponding blobs.
        The label map is rescaled such that it coincides with the reference map.
        """

        qimg_label_map = QImage(filename)
        qimg_label_map = qimg_label_map.convertToFormat(QImage.Format_RGB32)

        w = reference_map.width()
        h = reference_map.height()
        qimg_label_map = qimg_label_map.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

        label_map = utils.qimageToNumpyArray(qimg_label_map)
        label_map = label_map.astype(np.int32)

        # RGB -> label code association (ok, it is a dirty trick but it saves time..)
        label_coded = label_map[:, :, 0] + (label_map[:, :, 1] << 8) + (label_map[:, :, 2] << 16)

        labels = measure.label(label_coded, connectivity=1)

        too_much_small_area = 1000
        region_big = None

        created_blobs = []
        for region in measure.regionprops(labels):
            if region.area > too_much_small_area:
                id = len(self.seg_blobs)
                blob = Blob(region, 0, 0, self.progressive_id)
                self.progressive_id += 1

                # assign class
                row = region.coords[0, 0]
                col = region.coords[0, 1]
                color = label_map[row, col]

                for label_name in self.labels_info.keys():
                    c = self.labels_info[label_name]
                    if c[0] == color[0] and c[1] == color[1] and c[2] == color[2]:
                        blob.class_name = label_name
                        blob.class_color = c
                        break

                created_blobs.append(blob)

        return created_blobs


    def export_data_table_for_Scripps(self, scale_factor, filename):

        # create a list of properties
        properties = ['Class name', 'Centroid x', 'Centroid y', 'Coral area', 'Coral perimeter', 'Coral note']

        # create a list of instances
        name_list = []
        visible_blobs = []
        for blob in self.seg_blobs:

            if blob.qpath_gitem.isVisible():
                index = blob.blob_name
                name_list.append(index)
                visible_blobs.append(blob)

        number_of_seg = len(name_list)
        class_name = []
        centroid_x = np.zeros(number_of_seg)
        centroid_y = np.zeros(number_of_seg)
        coral_area = np.zeros(number_of_seg)
        coral_perimeter = np.zeros(number_of_seg)
        coral_maximum_diameter = np.zeros(number_of_seg)
        coral_note = []

        for i, blob in enumerate(visible_blobs):

            class_name.append(blob.class_name)
            centroid_x[i] = round(blob.centroid[0], 1)
            centroid_y[i] = round(blob.centroid[1], 1)
            coral_area[i] = round(blob.area * (scale_factor) * (scale_factor)/ 100,2)
            coral_perimeter[i] = round(blob.perimeter*scale_factor / 10,1)
            #coral_maximum_diameter[i] = blob.major_axis_length
            coral_note.append(blob.note)


        # create a dictionary
        dic = {
            'Class name': class_name,
            'Centroid x': centroid_x,
            'Centroid y': centroid_y,
            'Coral area': coral_area,
            'Coral perimeter': coral_perimeter,
            'Coral maximum diameter': coral_maximum_diameter,
            'Coral note': coral_note }

        # create dataframe
        df = pd.DataFrame(dic, columns=properties, index=name_list)
        df.to_csv(filename, sep='\t')


    def export_image_data_for_Scripps(self, map, filename):

        # create a black canvas of the same size of your map
        w = map.width()
        h = map.height()

        labelimg = QImage(w, h, QImage.Format_RGB32)
        labelimg.fill(qRgb(0, 0, 0))

        painter = QPainter(labelimg)

        pen = QPen(Qt.black)
        pen.setWidth(1)
        painter.setPen(pen)

        for i, blob in enumerate(self.seg_blobs):

            if blob.qpath_gitem.isVisible():

                if blob.class_name == "Empty":
                    rgb = qRgb(255, 255, 255)
                else:
                    class_color = self.labels_info[blob.class_name]
                    rgb = qRgb(class_color[0], class_color[1], class_color[2])

                painter.setBrush(QBrush(QColor(rgb)))
                painter.drawPath(blob.qpath_gitem.path())


        painter.end()

        labelimg.save(filename)


    def export_new_dataset(self, map, tile_size, step, output_folder):

        # if the dataset folder already had DL subfolder than delete them

        output_folder_training = os.path.join(output_folder, "training")
        output_folder_validation = os.path.join(output_folder, "validation")
        output_folder_test = os.path.join(output_folder, "test")

        if os.path.exists(output_folder_training):
            shutil.rmtree(output_folder_training, ignore_errors=True)
        if os.path.exists(output_folder_validation):
            shutil.rmtree(output_folder_validation, ignore_errors=True)
        if os.path.exists(output_folder_test):
            shutil.rmtree(output_folder_test, ignore_errors=True)

        # create DL folders

        os.mkdir(output_folder_training)
        output_images_training = os.path.join(output_folder_training, "images")
        output_labels_training = os.path.join(output_folder_training, "labels")
        os.mkdir(output_images_training)
        os.mkdir(output_labels_training)

        os.mkdir(output_folder_validation)
        output_images_validation = os.path.join(output_folder_validation, "images")
        output_labels_validation = os.path.join(output_folder_validation, "labels")
        os.mkdir(output_images_validation)
        os.mkdir(output_labels_validation)

        os.mkdir(output_folder_test)
        output_images_test = os.path.join(output_folder_test, "images")
        output_labels_test = os.path.join(output_folder_test, "labels")
        os.mkdir(output_images_test)
        os.mkdir(output_labels_test)

        ##### CREATE LABEL IMAGE

        # create a black canvas of the same size of your map
        w = map.width()
        h = map.height()

        labelimg = QImage(w, h, QImage.Format_RGB32)
        labelimg.fill(qRgb(0, 0, 0))

        painter = QPainter(labelimg)

        for i, blob in enumerate(self.seg_blobs):
            if blob.qpath_gitem.isVisible():
                if blob.qpath_gitem.isVisible():
                    if blob.class_name == "Empty":
                        rgb = qRgb(255, 255, 255)
                    else:
                        class_color = self.labels_info[blob.class_name]
                        rgb = qRgb(class_color[0], class_color[1], class_color[2])

                    painter.setBrush(QBrush(QColor(rgb)))
                    painter.drawPath(blob.qpath_gitem.path())

        painter.end()


        ##### TILING

        h1 = h * 0.65
        h2 = h * 0.85

        # tiles within the height [0..h1] are used for the training
        # tiles within the height [h1..h2] are used for the validation
        # the other tiles are used for the test

        tile_cols = int((w + tile_size) / step)
        tile_rows = int((h + tile_size) / step)

        deltaW = int(tile_size / 2) + 1
        deltaH = int(tile_size / 2) + 1

        for row in range(tile_rows):
            for col in range(tile_cols):

                top = row * step - deltaH
                left = col * step - deltaW
                cropimg = utils.cropQImage(map, [top, left, tile_size, tile_size])
                croplabel = utils.cropQImage(labelimg, [top, left, tile_size, tile_size])

                filenameRGB = ""

                if top + tile_size < h1 - step:

                    filenameRGB = os.path.join(output_images_training, "tile_" + str.format("{0:02d}", (row)) + "_" + str.format("{0:02d}", (col)) + ".png")
                    filenameLabel = os.path.join(output_labels_training, "tile_" + str.format("{0:02d}", (row)) + "_" + str.format("{0:02d}", (col)) + ".png")

                elif top > h2 + step:

                    filenameRGB = os.path.join(output_images_test, "tile_" + str.format("{0:02d}", (row)) + "_" + str.format("{0:02d}", (col)) + ".png")
                    filenameLabel = os.path.join(output_labels_test, "tile_" + str.format("{0:02d}", (row)) + "_" + str.format("{0:02d}", (col)) + ".png")

                elif top + tile_size >= h1 + step and top <= h2 - step:

                    filenameRGB = os.path.join(output_images_validation, "tile_" + str.format("{0:02d}", (row)) + "_" + str.format("{0:02d}", (col)) + ".png")
                    filenameLabel = os.path.join(output_labels_validation, "tile_" + str.format("{0:02d}", (row)) + "_" + str.format("{0:02d}", (col)) + ".png")

                print(filenameRGB)
                print(filenameLabel)

                if filenameRGB != "":
                    cropimg.save(filenameRGB)
                    croplabel.save(filenameLabel)


