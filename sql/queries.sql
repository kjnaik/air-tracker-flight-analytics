-- Q1: Total flights per aircraft model
SELECT aircraft_model AS model, COUNT(*) AS total_flights
FROM flights
WHERE aircraft_model IS NOT NULL
GROUP BY aircraft_model
ORDER BY total_flights DESC;

-- Q2: Aircraft assigned to more than 5 flights
SELECT f.aircraft_registration AS registration,
       COALESCE(a.model, MAX(f.aircraft_model)) AS model,
       COUNT(*) AS flight_count
FROM flights f
LEFT JOIN aircraft a ON f.aircraft_registration = a.registration
WHERE f.aircraft_registration IS NOT NULL
GROUP BY f.aircraft_registration, a.model
HAVING COUNT(*) > 5
ORDER BY flight_count DESC;

-- Q10: City pairs served by more than 2 different aircraft models
SELECT o.city AS origin_city, d.city AS destination_city,
       COUNT(DISTINCT f.aircraft_model) AS model_count
FROM flights f
JOIN airport o ON f.origin_iata = o.iata_code
JOIN airport d ON f.destination_iata = d.iata_code
WHERE f.aircraft_model IS NOT NULL
GROUP BY o.city, d.city
HAVING COUNT(DISTINCT f.aircraft_model) > 2
ORDER BY model_count DESC;