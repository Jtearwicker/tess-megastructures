J/MNRAS/529/1802    TESS SPOC FFI Main Sequence Target Sample     (Doyle+, 2024)
================================================================================
The TESS SPOC FFI target sample explored with Gaia.
    Doyle L., Armstrong D.J., Bayliss D., Rodel T., Kunovac V.
    <Mon. Not. R. Astron. Soc. 529, 1802-1813 (2024)>
    =2024MNRAS.529.1802D        (SIMBAD/NED BibCode)
================================================================================
ADC_Keywords: Stars, double and multiple ; Exoplanets ; Photometry ; Optical
Keywords: catalogues - surveys - planets and satellites: general -
          stars: fundamental parameters

Abstract:
    The Transiting Exoplanet Survey Satellite (TESS) mission has provided
    the community with high-precision times series photometry for ~2.8
    million stars across the entire sky via the Full Frame Image (FFI)
    light curves produced by the TESS Science Processing Operations Centre
    (SPOC). This set of light curves is an extremely valuable resource for
    the discovery of transiting exoplanets and other stellar science.
    However, due to the sample selection, this set of light curves does
    not constitute a magnitude limited sample. In order to understand the
    effects of this sample selection, we use Gaia DR2 and DR3 to study the
    properties of the stars in the TESS-SPOC FFI light curve set, with the
    aim of providing vital context for further research using the sample.
    We report on the properties of the TESS-SPOC FFI Targets in Sectors
    1-55 (covering Cycles 1-4). We cross-match the TESS-SPOC FFI Targets
    with the Gaia DR2 and DR3 catalogues of all targets brighter than Gaia
    magnitude 14 to understand the effects of sample selection on the
    overall stellar properties. This includes Gaia magnitude, parallax,
    radius, temperature, non-single star flags, luminosity, radial
    velocity and stellar surface gravity. In total, there are ~16.7
    million Gaia targets brighter than G=14, which when cross-matched with
    the TESS-SPOC FFI Targets leaves ~2.75 million. We investigate the
    binarity of each TESS-SPOC FFI Target and calculate the radius
    detection limit from two detected TESS transits which could be
    detected around each target. Finally, we create a comprehensive main
    sequence TESS-SPOC FFI Target sample which can be utilised in future
    studies.

Description:
    This catalogue is based off all TESS-SPOC FFI targets in sectors 1-55
    cross-matched with gaia DR2 and DR3. In total we have 30 available
    columns for each target including TIC ID, Gaia source ids and stellar
    properties. Amongst these we include the estimated detectable two
    transit radius detection limit for each target as the last column.

File Summary:
--------------------------------------------------------------------------------
 FileName      Lrecl  Records   Explanations
--------------------------------------------------------------------------------
ReadMe            80        .   This file
targets.dat      396  2319308   Main Sequence TESS-SPOC FFI targets
--------------------------------------------------------------------------------

See also:
    IV/38 : TESS Input Catalog - v8.0 (TIC-8) (Stassun+, 2019)
    I/345 : Gaia DR2 (Gaia Collaboration, 2018)
    I/355 : Gaia DR3 Part 1. Main source (Gaia Collaboration, 2022)

Byte-by-byte Description of file: targets.dat
--------------------------------------------------------------------------------
   Bytes Format Units     Label     Explanations
--------------------------------------------------------------------------------
   1- 10  I10   ---       TIC       TESS Input Catalogue ID (TIC_ID)
  12- 30  I19   ---       GaiaDR3   ? Gaia DR3 Source ID (dr3_source_id)
  32- 50  I19   ---       GaiaDR2   ? Gaia DR2 Source ID (dr2_source_id)
  52- 72 E21.19 deg       RAdeg     Right Ascension (ICRS) at Ep=2016.0 (ra)
  74- 95 E22.19 deg       DEdeg     Declination (ICRS) at Ep=2016.0 (dec)
  97- 98  I2    ---       Nsectors  Number of TESS Sectors Target was
                                     observed in (sectors_count)
 100-120 E21.18 mas       plx       Gaia DR3: Parallax (parallax)
 122-142 F21.19 mas     e_plx       Gaia DR3: Parallax error (parallax_error)
 144-166 F23.17 ---       Rplx      Gaia DR3: Parallax divided by its standard
                                     error (parallax_over_error)
 168-186 F19.16 mag       Gmag      ? Gaia DR3: G-band mean magnitude
                                     (phot_g_mean_mag)
 188-209 E22.17 mag       BP-RP     Gaia DR3: BP - RP colour (bp_rp)
 211-232 E22.17 km/s      RV        ? Gaia DR3: Radial Velocity
                                     (radial_velocity)
 234-253 F20.17 km/s    e_RV        ? Gaia DR3: Radial Velocity error
                                     (radial_velocity_error)
 255-273 F19.13 K         Teff      Gaia DR3: Effective temperature from
                                     GSP-Phot Aeneas best library using
                                     BP/RP spectra (teff_gspphot)
 275-292 F18.16 [cm/s2]   logg      Gaia DR3: Surface gravity from GSP-Phot
                                     Aeneas best library using BP/RP spectra
                                     (logg_gspphot)
 294-312 F19.16 ---       RUWE      Gaia DR3: Renormalised unit weight error
                                     (ruwe)
     314  I1    ---       NSS       Gaia DR3: Flag indicating the availability
                                     of additional information in the various
                                     Non-Single Star tables (non_single_star)
 316-337 E22.16 mag       GMAG      ? Absolute Magnitude in the G-band (abs_G)
 339-358 F20.17 Rsun      Rad       ? Stellar Radius from the TESS Input
                                     Catalogue (stellar_radius)
 360-373  E14.9 ppm       minNoise  ? TESS Combined Differential Photometric
                                     Precision from SPOC light curves
                                     (min_noise)
 375-396 F22.17 Earth     TwoRadius ? Planetary radius detection limit from two
                                     TESS transits (two_radius)
--------------------------------------------------------------------------------

Acknowledgements:
    Lauren Doyle, lauren.doyle(at)warwick.ac.uk

================================================================================
(End)                                        Patricia Vannier [CDS]  01-Mar-2024
