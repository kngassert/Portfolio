from netCDF4 import Dataset
import metpy.calc as mpcalc
from metpy.units import units
import numpy as np
from daymet_functions import downloadDaymetLatLonBox, createGridFile, cdoRemap, loadDaymetDims, saveNetCDF, mv2GoogleBucket, mergetime
from os import path, makedirs, remove
import glob

years = np.arange(1985, 2014 + 1)  # +1 to last year so it's included
region = 'na'  # 'na', 'pr', 'hi'
loc = 'JeffersonCoKY'
variables = ['pr']  # 'hurs', 'pr', 'rsds']  # if 'hurs' in variables, 'tas' must also be included. If 'tas' in variables, tasmax and tasmin will automatically be included.

tas_units, hurs_units, pr_units, rsds_units = 'K', '%', 'mm', 'W m-2'

lon1, lon2, lat1, lat2 = -86.0, -85.38, 37.98, 38.4

# if projection == latlon, user specifies regrid resolution (regrid_res, along with regrid_coarser_bool) to create a grid file, OR specifies a pre-existing grid file (grid_file) for remapping lcc -> latlon
projection = 'latlon'  # lcc or latlon
regrid_method = 'remapbil'  # cdo remap method to use for lcc -> latlon regrid
regrid_res = 0.008  # desired regrid resolution in degrees (0.008 deg ~= 1km longitude at equator)
regrid_coarser_bool = True  # if set to True and average resolution of data is coarser than 'regrid_res', data will be regrid to retain average (coarser) resolution of data
grid_file = ''  # pre-existing grid file (or netcdf) to use in remapping. If it doesn't exist, set to '' (emtpy string) and code will create a file based on 'regrid_res'

mounted_bucket_name = '<gcloud_bucket>'
ready4ba_save_path = f'Daymet/{loc}/ready4ba'

# path to file containing Google Cloud credentials
creds = f'{mounted_bucket_name}/gcloud_creds.json'

###

if not path.exists(f'{mounted_bucket_name}/{ready4ba_save_path}'):
    makedirs(f'{mounted_bucket_name}/{ready4ba_save_path}')

if grid_file == '':
    create_gridfile = True
    grid_file = f'{loc}_grid.txt'
else:
    create_gridfile = False

for year in years:    
    if 'tas' in variables:
        tmax_wget = downloadDaymetLatLonBox('tmax', loc, region, year, lon1, lon2, lat1, lat2)
        tmin_wget = downloadDaymetLatLonBox('tmin', loc, region, year, lon1, lon2, lat1, lat2)

        if projection == 'latlon':
            # remap from lcc to latlon grid
            tmax_fn = f'{loc}_tmax_daymet_{region}_regrid2latlon_{year}.nc'
            tmin_fn = f'{loc}_tmin_daymet_{region}_regrid2latlon_{year}.nc'

            if create_gridfile == True:
                print('creating grid file')
                # create grid file using tmax grid, then remap tmax and tmin
                createGridFile(tmax_wget, regrid_res, grid_file, regrid_coarser_bool)
            
            # remap using grid file
            cdoRemap(tmax_wget, tmax_fn, grid_file, regrid_method, '-z zip')
            cdoRemap(tmin_wget, tmin_fn, grid_file, regrid_method, '-z zip')

            # remove single-year raw files
            remove(tmax_wget)
            remove(tmin_wget)
            
        else:
            tmax_fn = tmax_wget
            tmin_fn = tmin_wget
            
        # open data
        tmax_file = Dataset(tmax_fn, 'r')
        tmin_file = Dataset(tmin_fn, 'r')
    
        tmax_data = tmax_file.variables['tmax'][:]
        tmin_data = tmin_file.variables['tmin'][:]

        # prep time info needed to save output .nc
        lats_input, lons_input, time_input, time_units = loadDaymetDims(tmax_file, year)
                
        tmax_file.close()
        tmin_file.close()

        if year % 4 == 0:  # leap year
            tmax_dec30_layer = np.expand_dims(tmax_data[-1], axis=0)
            tmin_dec30_layer = np.expand_dims(tmin_data[-1], axis=0)
            tmax_data = np.ma.concatenate((tmax_data, tmax_dec30_layer), axis=0)
            tmin_data = np.ma.concatenate((tmin_data, tmin_dec30_layer), axis=0)
          
        # calculate tas from tmax and tmin
        print('\ncalculating tas')
        tas_data = (tmax_data + tmin_data) / 2
        tas_pint = units.Quantity(tas_data, 'celsius')  # assign pint (attach Celsius units) for later hurs calculation
        
        # convert to Kelvin for saving .nc
        tmax_data = tmax_data + 273.15
        tmin_data = tmin_data + 273.15
        tas_data = tas_data + 273.15

        # save NetCDF
        save_fn = f'{loc}_tas_daymet_{region}_{year}_ready4ba.nc'
        description = 'Average temperature calculated from Daymet tmin and tmax with Python.'
        standard_name = 'daily average temperature'
        saveNetCDF(tas_data, 'tas', tas_units, save_fn, description, lats_input, \
                   lons_input, time_input, time_units, standard_name, projection)

        # prepare 'tasrange' so tasmax and tasmin can be bias-adjusted
        print('\ncalculating tasrange')
        tasrange_data = tmax_data - tmin_data

        save_fn = f'{loc}_tasrange_daymet_{region}_{year}_ready4ba.nc'
        description = 'Tasrange calculated from Daymet temperature data with Python.'
        standard_name = 'temperature range'
        saveNetCDF(tasrange_data, 'tasrange', tas_units, save_fn, description, lats_input, \
                   lons_input, time_input, time_units, standard_name, projection)

        # prepare 'tasskew' so tasmax and tasmin can be bias-adjusted
        print('\ncalculating tasskew')
        tasskew_data = (tas_data - tmin_data) / tasrange_data

        save_fn = f'{loc}_tasskew_daymet_{region}_{year}_ready4ba.nc'
        description = 'Tasskew calculated from Daymet temperature data with Python.'
        standard_name = 'temperature skew'
        saveNetCDF(tasskew_data, 'tasskew', tas_units, save_fn, description, lats_input, \
                   lons_input, time_input, time_units, standard_name, projection)

        
###
    if 'hurs' in variables:
        vp_wget = downloadDaymetLatLonBox('vp', loc, region, year, lon1, lon2, lat1, lat2)

        if projection == 'latlon':
            # remap from lcc to latlon grid
            vp_fn = f'{loc}_vp_daymet_{region}_regrid2latlon_{year}.nc'

            if create_gridfile == True:
                print('creating grid file')
                createGridFile(vp_wget, regrid_res, grid_file, regrid_coarser_bool)

            # remap using grid file
            cdoRemap(vp_wget, vp_fn, grid_file, regrid_method, '-z zip')

            remove(vp_wget)
            
        else:
            vp_fn = vp_wget
        
        # open regridded data
        vp_file = Dataset(vp_fn, 'r')  
        ea = vp_file.variables['vp'][:]

        # prep info needed to save output .nc
        lats_input, lons_input, time_input, time_units = loadDaymetDims(vp_file, year)

        vp_file.close()

        if year % 4 == 0:  # leap year
            ea_dec30_layer = np.expand_dims(ea[-1], axis=0)
            ea = np.ma.concatenate((ea, ea_dec30_layer), axis=0)
        
        # calculate saturation vp using tas
        print('\ncalculating saturation vapor pressure')
        es = mpcalc.saturation_vapor_pressure(tas_pint)  # hPa
    
        print('\ncalculating average relative humidity')
        hurs_data = (ea / es) * 100
        
        # save NetCDF
        save_fn = f'{loc}_hurs_daymet_{region}_{year}_ready4ba.nc'
        description = 'Average relative humidity calculated from Daymet tas (average of tmin and tmax) and vp with MetPy.'
        standard_name = 'average relative humidity'
        saveNetCDF(hurs_data, 'hurs', hurs_units, save_fn, description, lats_input, \
                   lons_input, time_input, time_units, standard_name, projection)
        
        
###
    if 'pr' in variables:
        pr_wget = downloadDaymetLatLonBox('prcp', loc, region, year, lon1, lon2, lat1, lat2)    

        if projection == 'latlon':
            # remap from lcc to latlon grid
            pr_fn = f'{loc}_pr_daymet_{region}_regrid2latlon_{year}.nc'

            if create_gridfile == True:
                print('creating grid file')
                createGridFile(pr_wget, regrid_res, grid_file, regrid_coarser_bool)

            # remap using grid file
            cdoRemap(pr_wget, pr_fn, grid_file, regrid_method, '-z zip')

            remove(pr_wget)
        
        else:
            pr_fn = pr_wget
            
        # open regridded data
        pr_file = Dataset(pr_fn, 'r')
        pr_data = pr_file.variables['prcp'][:]

        # prep info needed to save output .nc
        lats_input, lons_input, time_input, time_units = loadDaymetDims(pr_file, year)

        pr_file.close()

        if year % 4 == 0:  # leap year
            pr_dec30_layer = np.expand_dims(pr_data[-1], axis=0)
            pr_data = np.ma.concatenate((pr_data, pr_dec30_layer), axis=0)

        # save NetCDF
        save_fn = f'{loc}_pr_daymet_{region}_{year}_ready4ba.nc'  # use 'pr' instead of 'prcp' for ISIMIP BASD scripts
        description = 'Precipitation data from Daymet.'
        standard_name = 'precipitation'
        saveNetCDF(pr_data, 'pr', pr_units, save_fn, description, lats_input, \
                   lons_input, time_input, time_units, standard_name, projection)


###
    if 'rsds' in variables:
        srad_wget = downloadDaymetLatLonBox('srad', loc, region, year, lon1, lon2, lat1, lat2)
        dayl_wget = downloadDaymetLatLonBox('dayl', loc, region, year, lon1, lon2, lat1, lat2)

        if projection == 'latlon':
            # remap from lcc to latlon grid
            srad_fn = f'{loc}_srad_daymet_{region}_regrid2latlon_{year}.nc'
            dayl_fn = f'{loc}_dayl_daymet_{region}_regrid2latlon_{year}.nc'

            if create_gridfile == True:
                print('creating grid file')
                createGridFile(srad_wget, regrid_res, grid_file, regrid_coarser_bool)

            # remap using grid file
            cdoRemap(srad_wget, srad_fn, grid_file, regrid_method, '-z zip')
            cdoRemap(dayl_wget, dayl_fn, grid_file, regrid_method, '-z zip')

            remove(srad_wget)
            remove(dayl_wget)

        else:
            srad_fn = srad_wget        
            dayl_fn = dayl_wget

        # open regridded data
        srad_file = Dataset(srad_fn, 'r')
        dayl_file = Dataset(dayl_fn, 'r')

        srad = srad_file.variables['srad'][:]
        dayl = dayl_file.variables['dayl'][:]

        # prep info needed to save output .nc
        lats_input, lons_input, time_input, time_units = loadDaymetDims(srad_file, year)

        srad_file.close()
        dayl_file.close()

        if year % 4 == 0:  # leap year
            srad_dec30_layer = np.expand_dims(srad[-1], axis=0)
            dayl_dec30_layer = np.expand_dims(dayl[-1], axis=0)
            srad = np.ma.concatenate((srad, srad_dec30_layer), axis=0)
            dayl = np.ma.concatenate((dayl, dayl_dec30_layer), axis=0)

        # calculate rsds from srad
        print('\ncalculating surface downwelling shortwave radiation')
        rsds_data = srad * dayl / 86400

        # save NetCDF
        save_fn = f'{loc}_rsds_daymet_{region}_{year}_ready4ba.nc'
        description = 'Surface downwelling shortwave radiation calculated from Daymet srad and dayl using Python (rsds = srad * dayl / 86400).'
        standard_name = 'surface downwelling shortwave radiation'
        saveNetCDF(rsds_data, 'rsds', rsds_units, save_fn, description, lats_input, \
                   lons_input, time_input, time_units, standard_name, projection)


####

# merge data and upload to Google Cloud bucket path
if len(years) > 1:
    print('\nMerging and uploading data to Google Cloud')
else:
    print('\nUploading data to Google Cloud')

for var in variables:
    # Upload 'ready4ba' data to Google Cloud Bucket
    if len(years) > 1:  # merge single year files
        yr_filename = f'{loc}_{var}_daymet_{region}_????_ready4ba.nc'
        yrs_filename = f'{loc}_{var}_daymet_{region}_{years[0]}-{years[-1]}_ready4ba.nc'
        mergetime(yr_filename, yrs_filename)
    else:
        yrs_filename = f'{loc}_{var}_daymet_{region}_{years[0]}_ready4ba.nc'
    mv2GoogleBucket(yrs_filename, mounted_bucket_name, ready4ba_save_path, creds)    
    
    if var == 'tas':            
        # upload 'ready4ba' tasrange and tasskew too            
        for var2 in ['tasrange', 'tasskew']:
            if len(years) > 1:
                yr_filename = f'{loc}_{var2}_daymet_{region}_????_ready4ba.nc'
                yrs_filename = f'{loc}_{var2}_daymet_{region}_{years[0]}-{years[-1]}_ready4ba.nc'
                mergetime(yr_filename, yrs_filename)
            else:
                yrs_filename = f'{loc}_{var2}_daymet_{region}_{years[0]}_ready4ba.nc'
            mv2GoogleBucket(yrs_filename, mounted_bucket_name, ready4ba_save_path, creds)    

# remove data from current working directory (desired files have already been uploaded to Google Cloud bucket)
if projection == 'latlon':
    files2remove = glob.glob(f'{loc}_*_daymet_{region}_regrid2latlon_*.nc')
    # move grid file to Google Cloud
    mv2GoogleBucket(grid_file, mounted_bucket_name, ready4ba_save_path, creds)
    remove(grid_file)
else:
    files2remove = glob.glob(f'{loc}_*_daymet_{region}_v4_daily_*.nc')

for file in files2remove:
    try:
        remove(file)
    except:
        print(f'Error deleting {file}')
        pass

files2remove = glob.glob(f'{loc}_*_daymet_*_ready4ba.nc')
for file in files2remove:
    try:
        remove(file)
    except:
        print(f'Error deleting {file}')
        pass

print('done')
