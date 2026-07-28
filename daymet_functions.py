import wget
from netCDF4 import Dataset
import numpy as np
from google.cloud import storage
from cdo import Cdo
cdo = Cdo()
cdo.debug = True

def downloadDaymetLatLonBox(var, loc, region, year, lon1, lon2, lat1, lat2):
    '''
    
    Download a site-specific lat/lon box of Daymet data for a specified variable and year.

    Parameters
    ----------
    var : str
        Variable to download.
    loc : str
        Location of site-specific lat/lon box. Becomes prefix for saved data filename.
    region : str
        Daymet region dataset ('na', 'pr', 'hi').
    year : int
        Year for data download.
    lon1 : float
        West longitude of download box.
    lon2 : float
        East longitude of download box.
    lat1 : float
        South latitude of download box.
    lat2 : float
        North latitude of download box.

    Returns
    -------
    downloaded_filename : str
        Filename of downloaded data.
 
    '''

    if year % 4 == 0:  # leap year
        end_day = 30
    else:
        end_day = 31

    print(f'\nDownloading {var} data for {year}')
    downloaded_filename = wget.download(f'https://thredds.daac.ornl.gov/thredds/ncss/grid/ornldaac/2129/daymet_v4_daily_{region}_{var}_{year}.nc?var=lat&var=lon&var={var}&north={lat2}&west={lon1}&east={lon2}&south={lat1}&horizStride=1&time_start={year}-01-01T12:00:00Z&time_end={year}-12-{end_day}T12:00:00Z&timeStride=1&accept=netcdf',
                                 out = f'{loc}_{var}_daymet_{region}_v4_daily_{year}.nc')
    
    return downloaded_filename


###


def closestNumberDivisible(n, m):
    '''
    
    Find closest number (n) divisible by m
    
    Parameters
    ----------
    n : float
        Ballpark starting numerator, to find nearest number that is divisible by m.
    m : float
        Denominator to divide by in order to find number closest to n that returns a zero remainder.

    Returns
    -------
    n1 or n2 : float
        Closest number to n that is divisible by m.
 
    '''
    
    # Find the quotient
    q = int(n / m)
     
    # 1st possible closest number
    n1 = m * q
     
    # 2nd possible closest number
    if ((n * m) > 0) :
        n2 = (m * (q + 1))
    else :
        n2 = (m * (q - 1))
     
    # if true, then n1 is the required closest number
    if (abs(n - n1) < abs(n - n2)) :
        return n1
     
    # else n2 is the required closest number
    else:
        return n2


####


def createGridFile(nc_file, grid_resolution, grid_filename, coarser_default=False):
    '''

    Create grid text file for use in CDO remapping of NetCDF latlon data to new, user-specified resolution.    
                     
    Parameters
    ----------
    nc_file : str
        Filename (may or may not include a path) of NetCDF file that is to be regridded.
    grid_resolution : float
        Desired resolution of output grid, in degrees (e.g. 0.008 is ~1km at the equator).
    grid_filename : str
        Desired filename for text file that will be produced for regridding.
    coarser_default : boolean
        If set to True and average resolution of data is coarser than the specified 'grid_resolution', 
        the grid file will reflect the average (coarser) resolution of data. 
        Otherwise, the grid file will reflect the user-specified 'grid_resolution'.

    Returns
    -------
    NONE
        (Function saves a text file that CDO can use for regridding data; name == grid_filename).

    '''
    
    print(f'Creating grid information file for CDO remapping')
    nc_file_open = Dataset(nc_file, 'r')

    for l in ['lon', 'lat']:
        data = nc_file_open.variables[l][:]

        max_l, min_l = np.max(data), np.min(data)
        min_max_diff = max_l - min_l
        avg_res = np.abs(np.mean(np.diff(data)))  # avg resolution of original data

        # use average resolution if coarser than user-provided resolution and coarser_default==True
        if avg_res > grid_resolution and coarser_default == True:
            grid_res = avg_res
        else:
            grid_res = grid_resolution

        # calculate length of grid (and new max lat or lon) based on desired grid resolution
        closest_n_length_l = closestNumberDivisible(min_max_diff, grid_res)
        new_max_l = min_l + closest_n_length_l
        size_l = int(np.abs((new_max_l - min_l) / grid_res))

        if l == 'lon':
            min_lon = min_l
            xsize = size_l
            grid_res_lon = grid_res
        elif l == 'lat':
            min_lat = min_l
            ysize = size_l
            grid_res_lat = grid_res
            
    # write grid text file for cdo remapping
    gridsize = int(xsize * ysize)
        
    with open(grid_filename, 'w') as f:
        f.write('gridtype  = lonlat\n')
        f.write('xname = lon\n')
        f.write('yname = lat\n')
        f.write('xlongname = longitude\n')
        f.write('ylongname = latitude\n')
        f.write('xunits = degrees_east\n')
        f.write('yunits = degrees_north\n')
        f.write(f'xsize = {xsize}\n')
        f.write(f'ysize = {ysize}\n')
        f.write(f'xfirst = {min_lon}\n')
        f.write(f'yfirst = {min_lat}\n')
        f.write(f'xinc = {grid_res_lon}\n')
        f.write(f'yinc = {grid_res_lat}\n')
        f.write(f'gridsize = {gridsize}\n')

    nc_file_open.close()

    return

#####

def cdoRemap(input_filename, output_filename, grid_filename, remap_method, options):
    '''

    Regrid NetCDF latlon data to new resolution using a prepared grid text file.

    Parameters
    ----------
    input_filename : str
        Filename (may or may not include a path) of NetCDF file that is to be regridded.
    output_filename : str
        Filename (may or may not include a path) for regridded NetCDF file output.
    grid_filename : str
        Filename of prepared grid text file to use in CDO remapping.
    remap_method : str
        Desired CDO remap method (e.g. remapcon, remapbil, remapnn).
    options : str
        Text string to run in tandem with CDO remap command (e.g. '-z zip -setcalendar, proleptic_gregorian -chname,fwi,fwiday').

    Returns
    -------
    NONE
        (Output NetCDF file is saved to location specified in output_filename).
        
    '''
    
    print(f'Regridding {input_filename}')

    if remap_method == 'remapcon':  # First order conservative remapping
        cdo.remapcon(grid_filename, input=input_filename, output=output_filename, options=options)
    elif remap_method == 'remapcon2':  # Second order conservative remapping
        cdo.remapcon2(grid_filename, input=input_filename, output=output_filename, options=options)
    elif remap_method == 'remapbil':  # Bilinear interpolation
        cdo.remapbil(grid_filename, input=input_filename, output=output_filename, options=options)
    elif remap_method == 'remapnn':  # Nearest neighbor remapping
        cdo.remapnn(grid_filename, input=input_filename, output=output_filename, options=options)
    elif remap_method == 'remapdis':  # Distance-weighted average remapping
        cdo.remapdis(grid_filename, input=input_filename, output=output_filename, options=options)
    elif remap_method == 'remaplaf':  # Largest area fraction remapping
        cdo.remaplaf(grid_filename, input=input_filename, output=output_filename, options=options)

    return                                                                                                                                                                                                                                                              


#####


def loadDaymetDims(nc_file, year):
    '''

    Load Daymet NetCDF file (containing one year of data), return dimension data
    (lats, lons, time).
    Add extra day to time array for leap years (Daymet has no 12/31 in leap years).

    Parameters
    ----------
    nc_file : str
        Path to Daymet NetCDF file.
    year : int
        Year of data included in Daymet NetCDF file.

    Returns
    -------
    lats : 1D array
        Latitude values of file.
    lons : 1D array
        Longitude values of file.
    time : 1D array
        Time values of file.
    time_units : str
        String containing units of time (e.g. 'days since 1850-1-1 00:00:00').

    '''

    lats = nc_file.variables['lat'][:]    
    lons = nc_file.variables['lon'][:]
        
    time = nc_file.variables['time'][:]
    time_units = nc_file.variables['time'].units

    # if leap year, add extra day at end of year (12/31)
    if year % 4 == 0:
        time = np.append(time, time[-1] + 1)

    return lats, lons, time, time_units


####


def saveNetCDF(var_data, var_name, units, save_filename, description, lats, lons, time, time_units, standard_name, projection):
    '''
    
    Save NetCDF file based on input parameters.

    Parameters
    ----------
    var_data : ndarray
        Ndarray of data to save in output file.
    var_name : str
        Name of variable.
    units : str
        Units of variable.
    save_filename : str
        Filename for saved output file.
    description : str
        Description of variable to add to NetCDF metadata.
    lats : 1D (2D for lcc projection) array of floats
        Latitude values of data.
    lons : 1D (2D for lcc projection) array of floats
        Longitude values of data.
    time : 1D array of floats
        Time values of data.
    time_units : str
        String containing units of time (e.g. 'days since 1850-1-1 00:00:00').
    standard_name : str
        Full name of variable to save in NetCDF metadata.
    projection : str
        Projection of data; must be 'lcc' or 'latlon'

    Returns
    -------
    NONE
        (NetCDF file is saved as output)
        
    '''

    print(f'saving {var_name} .nc')
      
    out_file = Dataset(save_filename, 'w', format='NETCDF4')
    out_file.description = description
    out_file.createDimension('time', None)

    if projection == 'latlon':
        out_file.createDimension('lat', len(lats))
        out_file.createDimension('lon', len(lons))

        lon_var = out_file.createVariable('lon', np.float32, 'lon')
        lon_var.setncatts({'units': 'degrees_east', 'long_name': 'longitude', 'axis': 'X'})
        lat_var = out_file.createVariable('lat', np.float32, 'lat')
        lat_var.setncatts({'units': 'degrees_north', 'long_name': 'latitude', 'axis': 'Y'})

        var = out_file.createVariable(f'{var_name}', np.float32, ('time', 'lat', 'lon'), zlib=True, fill_value=np.nan)
        var.coordinates = 'lat lon'

    elif projection == 'lcc':
        out_file.createDimension('y', np.shape(lats)[0])
        out_file.createDimension('x', np.shape(lats)[1])  

        lon_var = out_file.createVariable('lon', np.float32, ('y', 'x'))
        lon_var.setncatts({'units': 'degrees_east', 'long_name': 'longitude'})
        lat_var = out_file.createVariable('lat', np.float32, ('y', 'x'))
        lat_var.setncatts({'units': 'degrees_north', 'long_name': 'latitude'})

        var = out_file.createVariable(f'{var_name}', np.float32, ('time', 'y', 'x'), zlib=True, fill_value=np.nan)
        var.coordinates = 'lat lon'
        var.grid_mapping = 'lambert_conformal_conic'

        proj_var = out_file.createVariable('lambert_conformal_conic', 'u2') # u2:16bit unsigned integer, no dimensions
        proj_var.grid_mapping_name = 'lambert_conformal_conic'
        proj_var.longitude_of_central_meridian = -100.0
        proj_var.latitude_of_projection_origin = 42.5
        proj_var.false_easting = 0.0
        proj_var.false_northing = 0.0
        proj_var.standard_parallel = (25.,  60.)
        proj_var.semi_major_axis = 6378137.0
        proj_var.inverse_flattening = 298.257223563

    else:
        print('ERROR: data projection must be lcc or latlon!')
    
    var.setncatts({'units': f'{units}', 'standard_name': f'{standard_name}', 'missing_value': np.nan})

    time_var = out_file.createVariable('time', np.float32, 'time')
    time_var.setncatts({'units': time_units, 'axis': 'T', 'calendar': 'proleptic_gregorian'})
        
    # write nc
    var[:, :, :] = var_data
    lon_var[:] = lons
    lat_var[:] = lats
    time_var[:] = time

    out_file.close()
    
        
###


def mv2GoogleBucket(filename, bucket, file_path_in_bucket, creds):
    '''
    
    Upload data to Google Cloud bucket.

    Parameters
    ----------
    filename : str
        Filename of data to upload.
    bucket : str
        Google Cloud bucket where data will be uploaded.
    file_path_in_bucket : str
        File path within bucket where data will be uploaded. If path does not exist, it will be created.
    creds : str
        Path and filename containing Google Cloud credential information.
    Returns
    -------
    NONE
        (File is uploaded to specified Google Cloud bucket path)

    '''
    
    print(f'Moving {filename} to Google Bucket')
    client = storage.Client.from_service_account_json(json_credentials_path=creds)
    bucket = client.get_bucket(bucket)
    save_file_path = f'{file_path_in_bucket}/{filename}'
    blob = bucket.blob(save_file_path)
    blob.upload_from_filename(f'{filename}')

    return


###


def mergetime(single_year_filename, all_year_filename):
    '''
    
    Merge multiple single-year NetCDF files into a single file

    Parameters
    ----------
    single_year_filename : str
        Filename for single year files (use wildcard in place of year).
    all_year_filename : str
        Output filename for merged file containing multiple years.

    Returns
    -------
    NONE
        (Files are merged into a single file)

    '''

    cdo.mergetime(input=f'{single_year_filename}', output=f'{all_year_filename}', options='-z zip')

    return
