"""
Geodispersion Calculator

Computes geodispersion as the sum of standard deviations of geographical 
and cultural distance across team members.
"""

import os
import csv
import math
import logging
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class GeodispersionCalculator:
    """
    Calculator for computing geodispersion based on geographical and cultural distances.
    """
    
    # Cache for loaded data
    _cities_data = None
    _hofstede_data = None
    
    @classmethod
    def _load_cities_data(cls):
        """Load and cache cities.csv data."""
        if cls._cities_data is not None:
            return cls._cities_data
        
        cities_path = os.path.join(os.path.dirname(__file__), '../datasets', 'cities.csv')
        cls._cities_data = {
            'by_city': {},          # city_name -> [records]
            'by_state': {},         # state_name -> [records]
            'by_country': {},       # country_name -> [records]
            'by_country_code': {},  # country_code -> [records]
        }
        
        with open(cities_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                city_name = row['name'].lower()
                state_name = row['state_name'].lower() if row['state_name'] else None
                state_code = row.get('state_code', '').lower() if row.get('state_code') else None
                country_name = row['country_name'].lower()
                country_code = row.get('country_code', '').lower() if row.get('country_code') else None
                
                # Store by city
                if city_name not in cls._cities_data['by_city']:
                    cls._cities_data['by_city'][city_name] = []
                cls._cities_data['by_city'][city_name].append(row)
                
                # Store by country code
                if country_code:
                    if country_code not in cls._cities_data['by_country_code']:
                        cls._cities_data['by_country_code'][country_code] = []
                    cls._cities_data['by_country_code'][country_code].append(row)
                
                # Store by state name
                if state_name:
                    if state_name not in cls._cities_data['by_state']:
                        cls._cities_data['by_state'][state_name] = []
                    cls._cities_data['by_state'][state_name].append(row)
                
                # Store by state code (e.g., CA, NY, TX)
                if state_code:
                    if state_code not in cls._cities_data['by_state']:
                        cls._cities_data['by_state'][state_code] = []
                    cls._cities_data['by_state'][state_code].append(row)
                
                # Store by country
                if country_name not in cls._cities_data['by_country']:
                    cls._cities_data['by_country'][country_name] = []
                cls._cities_data['by_country'][country_name].append(row)
        
        return cls._cities_data
    
    @classmethod
    def _load_hofstede_data(cls):
        """Load and cache cultural_distance_hofstede.csv data."""
        if cls._hofstede_data is not None:
            return cls._hofstede_data
        
        hofstede_path = os.path.join(os.path.dirname(__file__), '../datasets', 'cultural_distance_hosftede.csv')
        cls._hofstede_data = {}
        
        with open(hofstede_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                country = row['country'].lower()
                cls._hofstede_data[country] = {
                    'pdi': float(row['pdi']) if row['pdi'] else None,
                    'idv': float(row['idv']) if row['idv'] else None,
                    'mas': float(row['mas']) if row['mas'] else None,
                    'uai': float(row['uai']) if row['uai'] else None,
                    'lto': float(row['lto']) if row['lto'] else None,
                    'ivr': float(row['ivr']) if row['ivr'] else None,
                }
        
        return cls._hofstede_data
    
    @classmethod
    def _normalize_location(cls, location: str) -> str:
        """Normalize location string for matching."""
        if not location:
            return ""
        
        # Remove parentheses but keep content (e.g., 'Liège (BE)' -> 'Liège BE')
        import re
        location = re.sub(r'[()]', ' ', location)
        
        # Remove extra whitespace and convert to lowercase
        normalized = ' '.join(location.lower().split())
        
        # Remove common noise words and patterns
        noise_patterns = ['home', 'remote', 'online', 'near', 'light years away', '$rax']
        for pattern in noise_patterns:
            normalized = normalized.replace(pattern, '')
        
        # Clean up whitespace again
        normalized = ' '.join(normalized.split())
        return normalized
    
    @classmethod
    def _parse_location_parts(cls, location: str) -> dict:
        """
        Parse location string into city, state, country components.
        
        Returns dict with 'city', 'state', 'country' keys (values can be None).
        """
        # Normalize first
        location = cls._normalize_location(location)
        
        if not location:
            return {'city': None, 'state': None, 'country': None}
        
        # Common state/province codes for USA and Canada
        us_state_codes = {
            'al', 'ak', 'az', 'ar', 'ca', 'co', 'ct', 'de', 'fl', 'ga',
            'hi', 'id', 'il', 'in', 'ia', 'ks', 'ky', 'la', 'me', 'md',
            'ma', 'mi', 'mn', 'ms', 'mo', 'mt', 'ne', 'nv', 'nh', 'nj',
            'nm', 'ny', 'nc', 'nd', 'oh', 'ok', 'or', 'pa', 'ri', 'sc',
            'sd', 'tn', 'tx', 'ut', 'vt', 'va', 'wa', 'wv', 'wi', 'wy',
        }
        
        # Full US state names (common ones)
        us_state_names = {
            'alabama', 'alaska', 'arizona', 'arkansas', 'california', 'colorado',
            'connecticut', 'delaware', 'florida', 'georgia', 'hawaii', 'idaho',
            'illinois', 'indiana', 'iowa', 'kansas', 'kentucky', 'louisiana',
            'maine', 'maryland', 'massachusetts', 'michigan', 'minnesota',
            'mississippi', 'missouri', 'montana', 'nebraska', 'nevada',
            'new hampshire', 'new jersey', 'new mexico', 'new york',
            'north carolina', 'north dakota', 'ohio', 'oklahoma', 'oregon',
            'pennsylvania', 'rhode island', 'south carolina', 'south dakota',
            'tennessee', 'texas', 'utah', 'vermont', 'virginia', 'washington',
            'west virginia', 'wisconsin', 'wyoming',
        }
        
        # Country codes (ISO 3166-1 alpha-2) and common variations
        country_codes = {
            'us', 'usa', 'uk', 'gb', 'fr', 'de', 'it', 'es', 'pt', 'nl', 'be', 'ch',
            'at', 'dk', 'se', 'no', 'fi', 'pl', 'cz', 'hu', 'ro', 'bg', 'gr', 'tr',
            'ru', 'ua', 'cn', 'jp', 'kr', 'in', 'au', 'nz', 'br', 'ar', 'mx', 'ca'
        }
        
        # Country name variations (alternative names)
        country_variations = {
            'italia': 'italy',
            'deutschland': 'germany',
            'españa': 'spain',
            'brasil': 'brazil',
        }
        
        # Map country codes to full names
        country_code_map = {
            'us': 'united states', 'usa': 'united states',
            'uk': 'united kingdom', 'gb': 'united kingdom',
            'fr': 'france', 'de': 'germany', 'it': 'italy', 'es': 'spain',
            'nl': 'netherlands', 'be': 'belgium', 'ch': 'switzerland',
            'at': 'austria', 'pt': 'portugal',
        }
        
        # Try to split by common delimiters (comma or slash)
        parts = [p.strip() for p in location.replace('/', ',').split(',') if p.strip()]
        
        # Also try space-separated if no comma/slash found
        if len(parts) == 1 and ' ' in parts[0]:
            space_parts = parts[0].split()
            # Check if last part is a country code
            if len(space_parts) > 1 and space_parts[-1] in country_codes:
                parts = [' '.join(space_parts[:-1]), space_parts[-1]]
            # Check if last part is a known country name (for "Wuzhou China" case)
            elif len(space_parts) > 1:
                # Load cities data to check if last part is a country
                cities_data = cls._load_cities_data()
                last_part = space_parts[-1]
                if last_part in cities_data['by_country'] or last_part in cities_data['by_country_code']:
                    parts = [' '.join(space_parts[:-1]), last_part]
        
        result = {'city': None, 'state': None, 'country': None}
        
        if len(parts) == 1:
            # Single part - could be city, state, or country
            single = parts[0]
            # Apply country name variations
            if single in country_variations:
                single = country_variations[single]
            
            # Check if it's a country code first (higher priority than city name)
            if single in country_codes:
                single = country_code_map.get(single, single)
            
            result['city'] = single
        elif len(parts) == 2:
            # Two parts: could be "City, Country", "City, State", or "Country, City" (reversed)
            first, second = parts[0], parts[1]
            
            # Apply country name variations
            if second in country_variations:
                second = country_variations[second]
            if first in country_variations:
                first = country_variations[first]
            
            # Check if second part is a US state code FIRST (more common pattern)
            if second in us_state_codes:
                result['city'] = first
                result['state'] = second
                result['country'] = 'united states'
            # Check if second part is a full US state name
            elif second in us_state_names:
                result['city'] = first
                result['state'] = second
                result['country'] = 'united states'
            # Check if second part is a country code
            elif second in country_codes:
                result['city'] = first
                result['country'] = country_code_map.get(second, second)
            # Check if first part might be a country (reversed order: "Country, City")
            else:
                # Load cities data to check
                cities_data = cls._load_cities_data()
                first_is_country = (first in cities_data['by_country'] or 
                                  first in cities_data['by_country_code'])
                if first_is_country:
                    result['country'] = first
                    result['city'] = second
                else:
                    # Default: assume "City, Country/State"
                    result['city'] = first
                    result['country'] = second
        elif len(parts) >= 3:
            # Three+ parts: could be "City, State, Country" or "Country, State, City" (reversed)
            # Apply country variations
            for i in range(len(parts)):
                if parts[i] in country_variations:
                    parts[i] = country_variations[parts[i]]
            
            # Check if first part is a known country (reversed order)
            cities_data = cls._load_cities_data()
            first_is_country = (parts[0] in cities_data['by_country'] or 
                              parts[0] in cities_data['by_country_code'])
            
            if first_is_country:
                # Reversed: "Country, State/Province, City"
                result['country'] = parts[0]
                result['state'] = parts[1]
                result['city'] = parts[2]
            else:
                # Normal: "City, State, Country"
                result['city'] = parts[0]
                result['state'] = parts[1] if parts[1] not in country_codes else None
                # Handle country part (could be code or name)
                country_part = parts[2] if len(parts) > 2 else parts[1]
                if country_part in country_codes:
                    result['country'] = country_code_map.get(country_part, country_part)
                else:
                    result['country'] = country_part
        
        return result
    
    @classmethod
    def _match_location(cls, location: str) -> Optional[Dict]:
        """
        Match a location string to a record in cities.csv.
        
        Returns a dict with 'country', 'latitude', 'longitude' or None if no match.
        """
        if not location:
            return None
        
        cities_data = cls._load_cities_data()
        
        # Parse location into components
        parts = cls._parse_location_parts(location)
        
        # Strategy 1: If we have city and state, match within that state (most specific)
        if parts['city'] and parts['state']:
            city_key = parts['city']
            state_key = parts['state']
            
            # Check if it's a US state code or state name
            if city_key in cities_data['by_city']:
                matching_records = []
                for record in cities_data['by_city'][city_key]:
                    # Match by state code or state name
                    if (record.get('state_code', '').lower() == state_key or 
                        record.get('state_name', '').lower() == state_key):
                        matching_records.append(record)
                
                if matching_records:
                    # Prefer records with higher population
                    best_record = max(matching_records, 
                                    key=lambda r: int(r.get('population') or 0))
                    return {
                        'country': best_record['country_name'].lower(),
                        'latitude': float(best_record['latitude']),
                        'longitude': float(best_record['longitude'])
                    }
        
        # Strategy 2: If we have city and country (but not state), match within that country
        if parts['city'] and parts['country'] and not parts['state']:
            city_key = parts['city']
            country_key = parts['country']
            
            # Try to find city in specified country
            if city_key in cities_data['by_city']:
                matching_records = []
                for record in cities_data['by_city'][city_key]:
                    if record['country_name'].lower() == country_key:
                        matching_records.append(record)
                
                if matching_records:
                    # Prefer records with higher population
                    best_record = max(matching_records, 
                                    key=lambda r: int(r.get('population') or 0))
                    return {
                        'country': best_record['country_name'].lower(),
                        'latitude': float(best_record['latitude']),
                        'longitude': float(best_record['longitude'])
                    }
            
            # If city not found in that country, check if city is actually a state/province
            if city_key in cities_data['by_state']:
                for record in cities_data['by_state'][city_key]:
                    if record['country_name'].lower() == country_key:
                        # Use capital or largest city in that state
                        state_records = [r for r in cities_data['by_state'][city_key] 
                                       if r['country_name'].lower() == country_key]
                        if state_records:
                            best_record = max(state_records, 
                                            key=lambda r: int(r.get('population') or 0))
                            return {
                                'country': best_record['country_name'].lower(),
                                'latitude': float(best_record['latitude']),
                                'longitude': float(best_record['longitude'])
                            }
            
            # If nothing found, try country capital
            if country_key in cities_data['by_country']:
                records = cities_data['by_country'][country_key]
                capital = next((r for r in records if r.get('type') == 'capital'), None)
                if not capital:
                    # No capital, use city with highest population
                    capital = max(records, key=lambda r: int(r.get('population') or 0))
                return {
                    'country': capital['country_name'].lower(),
                    'latitude': float(capital['latitude']),
                    'longitude': float(capital['longitude'])
                }
        
        # Strategy 3: Single part - try as country first, then state, then city
        if parts['city'] and not parts['state'] and not parts['country']:
            single_key = parts['city']
            
            # Try as country
            if single_key in cities_data['by_country']:
                records = cities_data['by_country'][single_key]
                capital = next((r for r in records if r.get('type') == 'capital'), None)
                if not capital:
                    capital = max(records, key=lambda r: int(r.get('population') or 0))
                return {
                    'country': capital['country_name'].lower(),
                    'latitude': float(capital['latitude']),
                    'longitude': float(capital['longitude'])
                }
            
            # Try as state (get capital or largest city)
            if single_key in cities_data['by_state']:
                records = cities_data['by_state'][single_key]
                # Prefer capital of state
                capital = next((r for r in records if r.get('type') == 'capital'), None)
                if not capital:
                    # Use city with highest population in that state
                    capital = max(records, key=lambda r: int(r.get('population') or 0))
                return {
                    'country': capital['country_name'].lower(),
                    'latitude': float(capital['latitude']),
                    'longitude': float(capital['longitude'])
                }
            
            # Try as city - prefer larger cities (by population)
            if single_key in cities_data['by_city']:
                records = cities_data['by_city'][single_key]
                # Prefer records with higher population
                best_record = max(records, key=lambda r: int(r.get('population') or 0))
                return {
                    'country': best_record['country_name'].lower(),
                    'latitude': float(best_record['latitude']),
                    'longitude': float(best_record['longitude'])
                }
        
        return None
    
    @staticmethod
    def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate the great circle distance between two points on Earth (in kilometers).
        """
        # Convert to radians
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        # Radius of Earth in kilometers
        r = 6371
        
        return c * r
    
    @staticmethod
    def _calculate_geographic_distances(locations: List[Dict]) -> List[float]:
        """
        Calculate pairwise geographic distances between all locations.
        
        Returns a list of distances.
        """
        distances = []
        n = len(locations)
        
        for i in range(n):
            for j in range(i + 1, n):
                dist = GeodispersionCalculator._haversine_distance(
                    locations[i]['latitude'],
                    locations[i]['longitude'],
                    locations[j]['latitude'],
                    locations[j]['longitude']
                )
                distances.append(dist)
        
        return distances
    
    @classmethod
    def _calculate_cultural_distances(cls, locations: List[Dict]) -> List[float]:
        """
        Calculate pairwise cultural distances (Hofstede) between all locations.
        
        Returns a list of cultural distances.
        """
        hofstede_data = cls._load_hofstede_data()
        distances = []
        n = len(locations)
        
        for i in range(n):
            for j in range(i + 1, n):
                country1 = locations[i]['country']
                country2 = locations[j]['country']
                
                # Get Hofstede values for both countries
                h1 = hofstede_data.get(country1)
                h2 = hofstede_data.get(country2)
                
                if not h1 or not h2:
                    # Skip pairs where we don't have Hofstede data
                    continue
                
                # Calculate Euclidean distance across all Hofstede dimensions
                # that have values for both countries
                dim_distances = []
                for dim in ['pdi', 'idv', 'mas', 'uai', 'lto', 'ivr']:
                    v1 = h1.get(dim)
                    v2 = h2.get(dim)
                    if v1 is not None and v2 is not None:
                        dim_distances.append((v1 - v2) ** 2)
                
                if dim_distances:
                    cultural_dist = math.sqrt(sum(dim_distances))
                    distances.append(cultural_dist)
        
        return distances
    
    @staticmethod
    def _std_dev(values: List[float]) -> float:
        """Calculate standard deviation of a list of values."""
        if not values or len(values) < 2:
            return 0.0
        
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return math.sqrt(variance)
    
    # Maximum possible values for normalization
    _MAX_GEO_DISTANCE_KM = 20015.0       # Half Earth circumference
    _MAX_CULTURAL_DISTANCE = 200.0       # Empirical max across 6 Hofstede dims (each 0-100)

    @classmethod
    def compute(cls, repo_data: Dict) -> float:
        """
        Compute geodispersion score from repository data.
        
        Geodispersion is the sum of:
        - Standard deviation of geographical distances
        - Standard deviation of cultural distances (Hofstede metrics)
        
        Args:
            repo_data: Dictionary containing repository information with contributors
            
        Returns:
            float: Geodispersion score
        """
        # Extract repository object if nested
        if "repository" in repo_data:
            repo = repo_data["repository"]
        else:
            repo = repo_data
        
        contributors = repo.get("contributors", [])
        
        logger.debug(f"Starting geodispersion computation for {len(contributors)} contributors")
        
        if not contributors:
            logger.debug("No contributors found, returning 0.0")
            return 0.0
        
        # Match contributor locations
        matched_locations = []
        discarded_count = 0
        
        for contributor in contributors:
            login = contributor.get("login", "unknown")
            location_str = contributor.get("location", "")
            
            if not location_str:
                logger.debug(f"  ✗ {login}: No location provided")
                discarded_count += 1
                continue
            
            match = cls._match_location(location_str)
            if match:
                matched_locations.append(match)
                logger.debug(
                    f"  ✓ {login}: '{location_str}' → {match['country'].upper()} "
                    f"(lat: {match['latitude']:.4f}, lon: {match['longitude']:.4f})"
                )
            else:
                logger.debug(f"  ✗ {login}: '{location_str}' → No match found")
                discarded_count += 1
        
        logger.debug(f"Location matching complete: {len(matched_locations)} matched, {discarded_count} discarded")
        
        # Need at least 2 locations to calculate distances
        if len(matched_locations) < 2:
            logger.debug(f"Insufficient matched locations ({len(matched_locations)}), need at least 2. Returning 0.0")
            return 0.0
        
        # Calculate geographic distances
        logger.debug("\nCalculating geographic distances...")
        geo_distances = cls._calculate_geographic_distances(matched_locations)
        logger.debug(f"  Computed {len(geo_distances)} pairwise geographic distances")
        logger.debug(f"  Geographic distances (km): min={min(geo_distances):.2f}, max={max(geo_distances):.2f}, mean={sum(geo_distances)/len(geo_distances):.2f}")
        
        geo_std = cls._std_dev(geo_distances)
        logger.debug(f"  Geographic std dev: {geo_std:.2f} km")
        
        # Normalize geographic std dev to [0, 1]
        geo_std_normalized = geo_std / cls._MAX_GEO_DISTANCE_KM
        logger.debug(f"  Geographic std dev (normalized): {geo_std_normalized:.4f}")

        # Calculate cultural distances
        logger.debug("\nCalculating cultural distances (Hofstede)...")
        cultural_distances = cls._calculate_cultural_distances(matched_locations)
        logger.debug(f"  Computed {len(cultural_distances)} pairwise cultural distances")

        if cultural_distances:
            logger.debug(f"  Cultural distances: min={min(cultural_distances):.2f}, max={max(cultural_distances):.2f}, mean={sum(cultural_distances)/len(cultural_distances):.2f}")
            cultural_std = cls._std_dev(cultural_distances)
            logger.debug(f"  Cultural std dev: {cultural_std:.2f}")
            # Normalize cultural std dev to [0, 1]
            cultural_std_normalized = cultural_std / cls._MAX_CULTURAL_DISTANCE
            logger.debug(f"  Cultural std dev (normalized): {cultural_std_normalized:.4f}")
        else:
            logger.debug("  No cultural distances computed (missing Hofstede data for countries)")
            cultural_std_normalized = 0.0

        # Geodispersion is the sum of both normalized standard deviations (range: 0 to 2)
        geodispersion = geo_std_normalized + cultural_std_normalized
        logger.debug(f"\nFinal geodispersion score: {geo_std_normalized:.4f} + {cultural_std_normalized:.4f} = {geodispersion:.4f}")

        return geodispersion
