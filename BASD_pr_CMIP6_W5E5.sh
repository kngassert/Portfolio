mkdir ISIMIP_obs
mkdir ISIMIP_sim

var=pr
var_dir=precipitation
ssp=ssp585

data_path=gs://<data_path>
script_path=<script_path>

# copy W5E5 observation data from bucket to VM (0.5, 1, and 2 deg files)
gsutil -m cp "$data_path"/"$var_dir"/W5E5/"$var"_W5E5v2.0_1985-2014_ready4ba_* .

# spatially tile 0.5-deg W5E5 file for use in final downscaling step
cdo distgrid,24,12 "$var"_W5E5v2.0_1985-2014_ready4ba_0.5deg.nc ISIMIP_obs/"$var"_W5E5v2.0_1985-2014_ready4ba_0.5deg_ &
cdo distgrid,24,12 "$var"_W5E5v2.0_1985-2014_ready4ba_remap1deg.nc ISIMIP_obs/"$var"_W5E5v2.0_1985-2014_ready4ba_remap1deg_ &
wait
rm "$var"_W5E5v2.0_1985-2014_ready4ba_0.5deg.nc

# loop through models to bias adjust and downscale
for m in $(cat modelNames.txt);
do
	# copy prepped CMIP6 data from bucket to VM
	gsutil -m cp "$data_path"/"$var_dir"/"$ssp"/ready4ba/"$var"_"$m"_"$ssp"_1971-2100_ready4ba_remap*deg.nc .
	
	# 2-degree models (bias adjust @ 2 deg then downscale to 1 deg)
	if [ -f $var"_"$m"_"$ssp"_1971-2100_ready4ba_remap2deg.nc" ];
	then
		cdo selyear,1985/2014 "$var"_"$m"_"$ssp"_1971-2100_ready4ba_remap2deg.nc "$var"_"$m"_"$ssp"_1985-2014_ready4ba_remap2deg.nc
		
		python "$script_path"/bias_adjustment.py -o "$var"_W5E5v2.0_1985-2014_ready4ba_remap2deg.nc -s "$var"_"$m"_"$ssp"_1985-2014_ready4ba_remap2deg.nc -f "$var"_"$m"_"$ssp"_1971-2100_ready4ba_remap2deg.nc -b "$var"_"$m"_"$ssp"_1971-2100_ba_2deg.nc -v "$var" --lower-bound 0 --lower-threshold 0.1 -distribution gamma -t mixed --adjust-p-values 1 --n-processes 32 --step-size 1
		python "$script_path"/statistical_downscaling.py -o "$var"_W5E5v2.0_1985-2014_ready4ba_remap1deg.nc -s "$var"_"$m"_"$ssp"_1971-2100_ba_2deg.nc -f "$var"_"$m"_"$ssp"_1971-2100_ba_1deg.nc -v "$var" --lower-bound 0 --lower-threshold 0.1 --n-processes 32

	# 1-degree models (bias adjust @ 1 deg)
	elif [ -f $var"_"$m"_"$ssp"_1971-2100_ready4ba_remap1deg.nc" ];
	then
		cdo selyear,1985/2014 "$var"_"$m"_"$ssp"_1971-2100_ready4ba_remap1deg.nc "$var"_"$m"_"$ssp"_1985-2014_ready4ba_remap1deg.nc

		cdo distgrid,24,12 "$var"_"$m"_"$ssp"_1971-2100_ready4ba_remap1deg.nc ISIMIP_sim/"$var"_"$m"_"$ssp"_1971-2100_ready4ba_remap1deg_ &
		cdo distgrid,24,12 "$var"_"$m"_"$ssp"_1985-2014_ready4ba_remap1deg.nc ISIMIP_sim/"$var"_"$m"_"$ssp"_1985-2014_ready4ba_remap1deg_ &
		wait
		
		for i in {000..287};
		do
			python "$script_path"/bias_adjustment.py -o ISIMIP_obs/"$var"_W5E5v2.0_1985-2014_ready4ba_remap1deg_00"$i".nc -s ISIMIP_sim/"$var"_"$m"_"$ssp"_1985-2014_ready4ba_remap1deg_00"$i".nc -f ISIMIP_sim/"$var"_"$m"_"$ssp"_1971-2100_ready4ba_remap1deg_00"$i".nc -b ISIMIP_sim/"$var"_"$m"_"$ssp"_1971-2100_ba_1deg_00"$i".nc -v "$var" --lower-bound 0 --lower-threshold 0.1 -distribution gamma -t mixed --adjust-p-values 1 --n-processes 32 --step-size 1
		done

		rm ISIMIP_sim/"$var"_"$m"_"$ssp"_????-????_ready4ba_remap1deg_00*.nc

	# 0.5-degree models (bias adjust @ 0.5 deg)
	elif [ -f $var"_"$m"_"$ssp"_1971-2100_ready4ba_remap0.5deg.nc" ];
	then
		cdo selyear,1985/2014 "$var"_"$m"_"$ssp"_1971-2100_ready4ba_remap0.5deg.nc "$var"_"$m"_"$ssp"_1985-2014_ready4ba_remap0.5deg.nc

		cdo distgrid,24,12 "$var"_"$m"_"$ssp"_1971-2100_ready4ba_remap0.5deg.nc ISIMIP_sim/"$var"_"$m"_"$ssp"_1971-2100_ready4ba_remap0.5deg_ &
		cdo distgrid,24,12 "$var"_"$m"_"$ssp"_1985-2014_ready4ba_remap0.5deg.nc ISIMIP_sim/"$var"_"$m"_"$ssp"_1985-2014_ready4ba_remap0.5deg_ &
		wait

		for i in {000..287}; 
		do 
			python "$script_path"/bias_adjustment.py -o ISIMIP_obs/"$var"_W5E5v2.0_1985-2014_ready4ba_0.5deg_00"$i".nc -s ISIMIP_sim/"$var"_"$m"_"$ssp"_1985-2014_ready4ba_remap0.5deg_00"$i".nc -f ISIMIP_sim/"$var"_"$m"_"$ssp"_1971-2100_ready4ba_remap0.5deg_00"$i".nc -b "$var"_"$m"_"$ssp"_1971-2100_ba_0.5deg_00"$i".nc -v "$var" --lower-bound 0 --lower-threshold 0.1 -distribution gamma -t mixed --adjust-p-values 1 --n-processes 32 --step-size 1
		done
	fi

	rm "$var"_"$m"_"$ssp"_????-????_ready4ba_remap*deg.nc 
	
	# statistically downscale the bias-adjusted 1-deg file (or the bias-adjusted and downscaled 2 -> 1 deg file)
	if [ -f "ISIMIP_sim/"$var"_"$m"_"$ssp"_1971-2100_ba_1deg_00000.nc" ] || [ -f $var"_"$m"_"$ssp"_1971-2100_ba_1deg.nc" ]; then
		if [ -f $var"_"$m"_"$ssp"_1971-2100_ba_1deg.nc" ]; then
			cdo distgrid,24,12 "$var"_"$m"_"$ssp"_1971-2100_ba_1deg.nc ISIMIP_sim/"$var"_"$m"_"$ssp"_1971-2100_ba_1deg_ 
		fi

		for i in {000..287}; 
		do 
			python "$script_path"/statistical_downscaling.py -o ISIMIP_obs/"$var"_W5E5v2.0_1985-2014_ready4ba_0.5deg_00"$i".nc -s ISIMIP_sim/"$var"_"$m"_"$ssp"_1971-2100_ba_1deg_00"$i".nc -f "$var"_"$m"_"$ssp"_1971-2100_ba_0.5deg_00"$i".nc -v "$var" --lower-bound 0 --lower-threshold 0.1 --n-processes 32
		done
	fi

	# spatially de-tile 0.5-deg bias-adjusted and downscaled data
	cdo -z zip -setrtoc,-inf,0,0 -setrtoc,600,inf,600 -collgrid "$var"_"$m"_"$ssp"_1971-2100_ba_0.5deg_00* "$var"_"$m"_"$ssp"_1971-2100_ba_0.5deg.nc 
	
	rm "$var"_"$m"_"$ssp"_1971-2100_ba_0.5deg_00???.nc
	rm ISIMIP_sim/"$var"_"$m"_"$ssp"_????-????_*_00???.nc

	# calculate 95th percentile stats
	cdo -z zip -selyear,1971/2000 "$var"_"$m"_"$ssp"_1971-2100_ba_0.5deg.nc "$var"_"$m"_"$ssp"_1971-2000_ba_0.5deg.nc &
	cdo -z zip -selyear,2021/2050 "$var"_"$m"_"$ssp"_1971-2100_ba_0.5deg.nc "$var"_"$m"_"$ssp"_2021-2050_ba_0.5deg.nc &
	wait
	
	cdo -timpctl,95 "$var"_"$m"_"$ssp"_1971-2000_ba_0.5deg.nc -timmin "$var"_"$m"_"$ssp"_1971-2000_ba_0.5deg.nc -timmax "$var"_"$m"_"$ssp"_1971-2000_ba_0.5deg.nc timpctl95_"$var"_"$m"_"$ssp"_1971-2000_ba_0.5deg.nc
	cdo subc,5 -divc,109.57 -timsum -gt "$var"_"$m"_"$ssp"_2021-2050_ba_0.5deg.nc timpctl95_"$var"_"$m"_"$ssp"_1971-2000_ba_0.5deg.nc 2021-2050_changeInPercExceed_timpctl95_"$var"_"$m"_"$ssp"_1971-2000_ba_0.5deg.nc

        # save files to bucket, split by year
	cdo -z zip -splityear "$var"_"$m"_"$ssp"_1971-2100_ba_0.5deg.nc "$data_path"/"$var_dir"/"$ssp"/"$var"_"$m"_"$ssp"_basd_0.5deg_

	gsutil -m mv timpctl95_"$var"_"$m"_"$ssp"_1971-2000_ba_0.5deg.nc 2021-2050_changeInPercExceed_timpctl95_"$var"_"$m"_"$ssp"_1971-2000_ba_0.5deg.nc "$data_path"/stats/
	
	rm "$var"_"$m"_"$ssp"_????-????_ba_0.5deg.nc 
done &&

rm "$var"_W5E5v2.0_1985-2014_ready4ba_remap?deg.nc
rm -r ISIMIP_obs
rm -r ISIMIP_sim
