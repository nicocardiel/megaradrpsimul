#
# Copyright 2025 Universidad Complutense de Madrid
#
# This file is part of megaradrpsimul.
#
# SPDX-License-Identifier: GPL-3.0-or-later
# License-Filename: LICENSE
#

"""Simulate frames for MEGARA data reduction."""

from astropy import units as u
from astropy.io import fits
from tqdm import tqdm

import numpy as np
import pickle
import teareduce as tea

from .cosmicray_cleaning import cosmicray_cleaning
from .smooth_frames import smooth_frames
from .simulation_run_save import simulation_run_save
from .calculate_bias_readout_noise import calculate_bias_readout_noise
from .simulate_frames_step import simulate_frames_step
from .open_read_yaml_simulation import open_read_yaml_simulation

def simulate_frames(megara_dir, data_work_dir, work_megara_dir):
    """Simulate frames for MEGARA data reduction.
    This function simulates the frames for the MEGARA data reduction process.
    It processes bias, trace map, arc calibration, LcbImage, and science object frames.
    
    Parameters
    ----------
    megara_dir : Path instance
        Path to the MEGARA directory.
    work_dir : Path instance
        Path to the work directory.
    work_megara_dir : Path instance
        Path to the work MEGARA directory.
   
    """
    
    print('starting simulation of frames')

    #.................................... BIAS ..........................................
    yaml_file_bias = list(work_megara_dir.glob('0_*.yaml'))[0]   # it is a path instance
    list_bias = open_read_yaml_simulation(megara_dir, yaml_file_bias)
    print('creating bias frames list')
    
    bias_cleaned_images = cosmicray_cleaning(list_bias)
    bias_smoothed_images = smooth_frames(bias_cleaned_images)

    with open(work_megara_dir/'smoothed_bias.pkl', 'wb') as f:
        pickle.dump(bias_smoothed_images, f)

    #with open(work_megara_dir/'smoothed_bias.pkl', 'rb') as f:
    #    bias_smoothed_images = pickle.load(f)

    # Median of all the smoothed bias images:
    list_smoothed_bias = list(bias_smoothed_images.values())
    stack_smoothed_images = np.stack(list_smoothed_bias, axis=0)      
    bias_smoothed_median = np.median(stack_smoothed_images, axis=0)

    # we convert to integer and round the values to avoid problems with the data type
    bias_smoothed_median_round = np.round(bias_smoothed_median).astype(np.uint16)

    # Bias generators
    bias_generators = {}
    all_noise_arrays = []

    for idx, img_path in tqdm(enumerate(list_bias), total=len(list_bias), desc="Image processing", unit="img"):
        with fits.open(img_path) as hdul:
            data = hdul[0].data  
            naxis2, naxis1 = data.shape
        
        # Calculate the noise for each of the CCDs
        noise_array = calculate_bias_readout_noise(data, bias_smoothed_images[f"smoothed_{idx}"], naxis2, naxis1)
        all_noise_arrays.append(noise_array)

        bias_image_generator = tea.SimulateCCDExposure(
            naxis1=naxis1, naxis2=naxis2, bitpix=16,
            bias=bias_smoothed_images[f"smoothed_{idx}"] * u.adu,
            readout_noise = noise_array * u.adu 
        )
        
        # Save the generator as "generator_{idx}"
        generator_name = f"generator_{idx}"
        bias_generators[generator_name] = bias_image_generator

    print('Bias generators created')

    all_noise_arrays = np.array(all_noise_arrays)
    #readout_noise_mean = np.mean(all_noise_arrays, axis=0) 
    readout_noise_median = np.median(all_noise_arrays, axis=0)

    # Simulation of bias images:
    for idx, img_path in tqdm(enumerate(list_bias), total=len(list_bias), desc="Simulating bias images", unit="img"):
        generator_name = f"generator_{idx}"
        generator = bias_generators[generator_name]
        simulation_run_save(data_work_dir, img_path, generator, type_image='bias')

    print('\033[1m\033[34m ' + "all bias images have been simulated" + '\033[0m\n')

    #.................................... Gain ..........................................
    # Gain values from header keywords
    gain_top = 1.6 * (u.electron/u.adu) 
    gain_bottom = 1.73 * (u.electron/u.adu)
    gain_array = np.full((naxis2, naxis1), gain_top.value)
    gain_array[0:2106, :] = gain_bottom.value

    #.................................... TRACEMAP ..........................................
    yaml_file_traces = list(work_megara_dir.glob('1_*.yaml'))[0]
    list_traces = open_read_yaml_simulation(megara_dir, yaml_file_traces)
    simulate_frames_step(list_images=list_traces, 
                        naxis1=naxis1,naxis2=naxis2,
                        data_work_dir=data_work_dir,
                        name_step='TraceMap',
                        bias_smoothed_median=bias_smoothed_median_round,
                        gain_array=gain_array,
                        readout_noise_median=readout_noise_median) 
    
    print('\033[1m\033[34m ' + "all TraceMap images have been simulated" + '\033[0m\n')


    #.................................... ArcCalibration ....................................
    yaml_file_arc = list(work_megara_dir.glob('3_*b.yaml'))[0]  # adding the b helps us distinguish between 3_WaveCalib.yaml and 3_WaveCalib_check.yaml
    list_arc = open_read_yaml_simulation(megara_dir, yaml_file_arc)
    
    simulate_frames_step(list_images=list_arc,
                        naxis1=naxis1,naxis2=naxis2,
                        data_work_dir=data_work_dir,
                        name_step='ArcCalibration',
                        bias_smoothed_median=bias_smoothed_median_round,
                        gain_array=gain_array,
                        readout_noise_median=readout_noise_median)
    
    print('\033[1m\033[34m ' + "all ArcCalibration images have been simulated" + '\033[0m\n')
    
    # ..................................LcbImage Star ..........................................
    yaml_file_lcb = list(work_megara_dir.glob('6_*.yaml'))[0]   # it is a path instance
    list_lcb = open_read_yaml_simulation(megara_dir, yaml_file_lcb)
    
    simulate_frames_step(list_images=list_lcb,
                        naxis1=naxis1,naxis2=naxis2,
                        data_work_dir=data_work_dir,
                        name_step='LcbImage',
                        bias_smoothed_median=bias_smoothed_median_round,
                        gain_array=gain_array,
                        readout_noise_median=readout_noise_median)
    
    print('\033[1m\033[34m ' + "all LcbImage images have been simulated" + '\033[0m\n')

    # ..................................Science Object ..........................................
    yaml_file_lcb_object = list(work_megara_dir.glob('8_*.yaml'))[0]   # it is a path instance
    list_lcb_object = open_read_yaml_simulation(megara_dir, yaml_file_lcb_object)
    simulate_frames_step(list_images=list_lcb_object,
                        naxis1=naxis1,naxis2=naxis2,
                        data_work_dir=data_work_dir,
                        name_step='Science LcbImage',
                        bias_smoothed_median=bias_smoothed_median_round,
                        gain_array=gain_array,
                        readout_noise_median=readout_noise_median)
    
    print('\033[1m\033[34m ' + "all LcbImage Object images have been simulated" + '\033[0m\n')