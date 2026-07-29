import pandas as pd
from os import path, makedirs
import glob
from multiprocessing import Pool
from cdo import Cdo
cdo = Cdo()
cdo.debug = True


num_processes = 8

# specify path of warming levels .csv
working_dir = '<working_dir>'
bucket_path = '<gcloud_bucket>'
warming_levels_csv = 'ISIMIP_BASD_warming_levels.csv'

# merge single year NetCDFs based on warming levels, start years, and end years in spreadsheet
def warming_levels_merge(chunk):
    ssp = 'ssp585'

    # variable dictionary (key = long name, value = short name)
    var_name = {
                'precipitation': 'pr'
#                'maximum_temperature': 'tasmax'
                }

    for row in range(len(chunk)):
        row = chunk.iloc[row]

        # iterate over variables to make warming level files
        for var_long, var_short in var_name.items():
            # specify paths of data and saved output, create save path if it doesn't exist
            data_path = f'{working_dir}/{bucket_path}/{var_long}/{ssp}'
            save_path = f'{working_dir}/warming_levels'

            # create list of input data filenames for each warming level
            input_fns = ['{}/{}_{}_{}_basd_0.5deg_{}.nc'.format(data_path, var_short, row['Model'], ssp, i) for i in range(int(row['Start Year']), int(row['End Year']) + 1)]

            output_fn = f'{save_path}/{var_short}_{row["Model"]}_{ssp}_basd_0.5deg_{row["Warming Level"]}.nc'

            # check that all files in warming level exist before performing merge
            check_input_files_exist = [path.isfile(f) for f in input_fns]

            if all(check_input_files_exist) == False:
                print(f'Warning! Skipping warming level {row["Warming Level"]} for {row["Model"]} {var_short}. Missing files: {[fn for fn, bool in zip(input_fns, check_input_files_exist) if bool == False]}.')
            else:
                cdo.mergetime(input='-apply,-selname,{} [ {} ]'.format(var_short, ' '.join(input_fns)), output=output_fn, options='-z zip')

    return

##############

# read in warming levels dataframe
wl_df = pd.read_csv(warming_levels_csv)

chunks = [wl_df[i::num_processes] for i in range(num_processes)]

# merge single year files based on warming level and model name
with Pool(num_processes) as pool:
    pool.map(warming_levels_merge, chunks)

print('done')
