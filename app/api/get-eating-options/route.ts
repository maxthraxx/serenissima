import { NextResponse } from 'next/server';
import Airtable, { FieldSet, Record as AirtableRecord } from 'airtable';

// Airtable Configuration (Assurez-vous que ces variables d'environnement sont définies)
const AIRTABLE_API_KEY = process.env.AIRTABLE_API_KEY;
const AIRTABLE_BASE_ID = process.env.AIRTABLE_BASE_ID;

const MAX_CLOSEST_PROVIDERS_PER_TYPE = 10; // Limite pour chaque type de fournisseur

// Helper function to calculate Haversine distance
function calculateHaversineDistance(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371e3; // metres
  const φ1 = lat1 * Math.PI/180; // φ, λ in radians
  const φ2 = lat2 * Math.PI/180;
  const Δφ = (lat2-lat1) * Math.PI/180;
  const Δλ = (lon2-lon1) * Math.PI/180;

  const a = Math.sin(Δφ/2) * Math.sin(Δφ/2) +
            Math.cos(φ1) * Math.cos(φ2) *
            Math.sin(Δλ/2) * Math.sin(Δλ/2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));

  const d = R * c; // in metres
  return d;
}

// Helper function to get building position
function getBuildingPosition(buildingFields: FieldSet): { lat: number; lng: number } | null {
  if (buildingFields.Position && typeof buildingFields.Position === 'string') {
    try {
      const pos = JSON.parse(buildingFields.Position as string);
      if (typeof pos.lat === 'number' && typeof pos.lng === 'number') {
        return pos;
      }
    } catch (e) { /* ignore */ }
  }
  // Fallback to Point field if Position is not valid or not present
  if (buildingFields.Point && typeof buildingFields.Point === 'string') {
    const parts = (buildingFields.Point as string).split('_');
    if (parts.length >= 3) { // Expecting format like "type_lat_lng" or "type_lat_lng_index"
      try {
        const lat = parseFloat(parts[1]);
        const lng = parseFloat(parts[2]);
        if (!isNaN(lat) && !isNaN(lng)) {
          return { lat, lng };
        }
      } catch (e) { /* ignore */ }
    }
  }
  return null;
}

if (!AIRTABLE_API_KEY || !AIRTABLE_BASE_ID) {
  throw new Error('Airtable API key or Base ID is not configured in environment variables for get-eating-options.');
}

const airtable = new Airtable({ apiKey: AIRTABLE_API_KEY }).base(AIRTABLE_BASE_ID);

// Helper to escape single quotes for Airtable formulas
function escapeAirtableValue(value: string | number | boolean): string {
  if (typeof value === 'string') {
    return value.replace(/'/g, "\\'");
  }
  return String(value);
}

const FOOD_RESOURCE_TYPES = [
  // Raw Food Materials
  "grain", "olives", "vegetables", "fish", "meat", "game_meat", "salt", "spices",
  // Processed Food Materials
  "flour", "olive_oil", "preserved_fish",
  // Finished Food Products
  "bread", "cheese", "pastries", "sugar_confections", "wine", "spiced_wine"
  // "fruit" was in the old list, "ale", "cider", "mead", "spirits", "cooked_meal", "water_skin_potable" are removed based on new list.
];

interface EatingOption {
  source: 'inventory' | 'home' | 'tavern' | 'retail_food_shop';
  details: string; 
  resourceType?: string;
  buildingId?: string;
  buildingName?: string;
  price?: number;
  quantity?: number;
  contractId?: string; // Ajout pour la cohérence
}

interface FormattedAirtableRecord {
  id: string;
  fields: Record<string, any>;
}

async function fetchCitizenByName(username: string): Promise<FormattedAirtableRecord | null> {
  try {
    const records = await airtable('CITIZENS').select({
      filterByFormula: `{Username} = '${escapeAirtableValue(username)}'`,
      maxRecords: 1,
    }).firstPage();
    if (records.length > 0) {
      return { id: records[0].id, fields: records[0].fields };
    }
    return null;
  } catch (error) {
    console.error(`Error fetching citizen ${username}:`, error);
    return null;
  }
}

async function fetchCitizenHome(username: string): Promise<FormattedAirtableRecord | null> {
  try {
    const records = await airtable('BUILDINGS').select({
      filterByFormula: `AND({Occupant} = '${escapeAirtableValue(username)}', {Category} = 'home')`,
      maxRecords: 1,
    }).firstPage();
    if (records.length > 0) {
      return { id: records[0].id, fields: records[0].fields };
    }
    return null;
  } catch (error) {
    console.error(`Error fetching home for citizen ${username}:`, error);
    return null;
  }
}

async function fetchResources(
  assetType: 'citizen' | 'building',
  assetId: string, // Username for citizen, BuildingId (custom) for building
  ownerUsername: string,
  resourceTypes: string[]
): Promise<FormattedAirtableRecord[]> {
  if (resourceTypes.length === 0) return [];
  const resourceTypeFilters = resourceTypes.map(rt => `{Type} = '${escapeAirtableValue(rt)}'`);
  const orFilter = `OR(${resourceTypeFilters.join(', ')})`;
  
  try {
    const formula = `AND({AssetType} = '${escapeAirtableValue(assetType)}', {Asset} = '${escapeAirtableValue(assetId)}', {Owner} = '${escapeAirtableValue(ownerUsername)}', ${orFilter})`;
    const records = await airtable('RESOURCES').select({
      filterByFormula: formula,
    }).all();
    return records.map(r => ({ id: r.id, fields: r.fields }));
  } catch (error) {
    console.error(`Error fetching resources for ${assetType} ${assetId}, owner ${ownerUsername}:`, error);
    return [];
  }
}

async function fetchTavernsWithFood(
  resourceTypes: string[],
  citizenPosition: { lat: number; lng: number } | null,
  limit: number
): Promise<any[]> {
  if (resourceTypes.length === 0) return [];
  const resourceTypeFilters = resourceTypes.map(rt => `{ResourceType} = '${escapeAirtableValue(rt)}'`);
  const orResourceTypeFilter = `OR(${resourceTypeFilters.join(', ')})`;

  try {
    // 1. Fetch all taverns/inns
    let tavernRecordsRaw = await airtable('BUILDINGS').select({
      filterByFormula: "AND(OR({Type}='tavern', {Type}='inn'), {IsConstructed}=TRUE())",
      fields: ["BuildingId", "Name", "Type", "Position", "Point"] 
    }).all();

    if (tavernRecordsRaw.length === 0) return [];

    let processedTaverns = tavernRecordsRaw.map(r => ({ id: r.id, fields: r.fields as FieldSet }));

    if (citizenPosition) {
      const tavernsWithDistance = processedTaverns.map(tavern => {
        const pos = getBuildingPosition(tavern.fields);
        const distance = pos ? calculateHaversineDistance(citizenPosition.lat, citizenPosition.lng, pos.lat, pos.lng) : Infinity;
        return { ...tavern, distance };
      }).filter(tavern => tavern.distance !== Infinity);

      tavernsWithDistance.sort((a, b) => a.distance - b.distance);
      processedTaverns = tavernsWithDistance.slice(0, limit);
      console.log(`[get-eating-options] fetchTavernsWithFood: Filtered ${tavernRecordsRaw.length} taverns down to ${processedTaverns.length} closest ones.`);
    }


    const tavernFoodOffers = [];

    // 2. For each (potentially filtered) tavern, fetch its active food contracts
    for (const tavern of processedTaverns) {
      const tavernBuildingId = tavern.fields.BuildingId as string;
      const tavernName = tavern.fields.Name as string || tavernBuildingId;
      if (!tavernBuildingId) continue;

      const contractFormula = `AND({SellerBuilding} = '${escapeAirtableValue(tavernBuildingId)}', {Type} = 'public_sell', {Status} = 'active', ${orResourceTypeFilter})`;
      const foodContracts = await airtable('CONTRACTS').select({
        filterByFormula: contractFormula,
        fields: ["ResourceType", "PricePerResource", "TargetAmount", "ContractId"]
      }).all();

      for (const contract of foodContracts) {
        tavernFoodOffers.push({
          tavernId: tavernBuildingId,
          tavernName: tavernName,
          resourceType: contract.fields.ResourceType,
          price: contract.fields.PricePerResource,
          quantityAvailable: contract.fields.TargetAmount,
          contractId: contract.fields.ContractId || contract.id,
        });
      }
    }
    return tavernFoodOffers;
  } catch (error) {
    console.error(`Error fetching taverns with food:`, error);
    return [];
  }
}

// Modifié pour retourner aussi un journal de débogage
async function fetchRetailFoodOffers(
  resourceTypes: string[],
  citizenPosition: { lat: number; lng: number } | null,
  limit: number
): Promise<{ offers: EatingOption[], debugLog: any[] }> {
  if (resourceTypes.length === 0) return { offers: [], debugLog: [] };
  const resourceTypeFilters = resourceTypes.map(rt => `{ResourceType} = '${escapeAirtableValue(rt)}'`);
  const orResourceTypeFilter = `OR(${resourceTypeFilters.join(', ')})`;

  const debugRetailFoodOffers: any[] = [];

  try {
    // 1. Fetch all retail_food buildings
    let retailShopRecordsRaw = await airtable('BUILDINGS').select({
      filterByFormula: "AND({SubCategory}='retail_food', {IsConstructed}=TRUE())",
      fields: ["BuildingId", "Name", "Type", "Owner", "RunBy", "Position", "Point"] 
    }).all();

    if (retailShopRecordsRaw.length === 0) return { offers: [], debugLog: [] };
    
    let processedShops = retailShopRecordsRaw.map(r => ({ id: r.id, fields: r.fields as FieldSet }));

    if (citizenPosition) {
      const shopsWithDistance = processedShops.map(shop => {
        const pos = getBuildingPosition(shop.fields);
        const distance = pos ? calculateHaversineDistance(citizenPosition.lat, citizenPosition.lng, pos.lat, pos.lng) : Infinity;
        return { ...shop, distance };
      }).filter(shop => shop.distance !== Infinity);

      shopsWithDistance.sort((a, b) => a.distance - b.distance);
      processedShops = shopsWithDistance.slice(0, limit);
      console.log(`[get-eating-options] fetchRetailFoodOffers: Filtered ${retailShopRecordsRaw.length} shops down to ${processedShops.length} closest ones.`);
    }

    const retailFoodShopOffers = [];

    for (const shop of processedShops) {
      const shopBuildingId = shop.fields.BuildingId as string;
      const shopName = shop.fields.Name as string || shopBuildingId;
      const shopOwnerOrOperator = (shop.fields.RunBy || shop.fields.Owner) as string;

      if (!shopBuildingId || !shopOwnerOrOperator) continue;

      const contractFormula = `AND({SellerBuilding} = '${escapeAirtableValue(shopBuildingId)}', {Type} = 'public_sell', {Status} = 'active', ${orResourceTypeFilter})`;
      const foodContracts = await airtable('CONTRACTS').select({
        filterByFormula: contractFormula,
        fields: ["ResourceType", "PricePerResource", "TargetAmount", "ContractId", "Seller"]
      }).all();
      
      const shopContractsDebug = {
        shopId: shopBuildingId,
        shopName: shopName,
        shopOwnerOrOperator: shopOwnerOrOperator,
        contractQuery: contractFormula,
        contractsFound: foodContracts.map(c => ({id: c.id, fields: c.fields})),
        stockChecks: [] as any[]
      };

      for (const contract of foodContracts) {
        const resourceToBuy = contract.fields.ResourceType as string;
        const price = contract.fields.PricePerResource as number;
        const contractSeller = contract.fields.Seller as string;

        // Ensure the contract seller matches the shop owner/operator for stock ownership consistency
        if (contractSeller !== shopOwnerOrOperator) {
            shopContractsDebug.stockChecks.push({
                resourceType: resourceToBuy,
                contractId: contract.id,
                status: `Skipped: Contract seller (${contractSeller}) does not match shop owner/operator (${shopOwnerOrOperator}).`
            });
            continue;
        }

        const stockCheckFormula = `AND({Asset} = '${escapeAirtableValue(shopBuildingId)}', {AssetType} = 'building', {Owner} = '${escapeAirtableValue(shopOwnerOrOperator)}', {Type} = '${escapeAirtableValue(resourceToBuy)}', {Count} > 0)`;
        const stockRecords = await airtable('RESOURCES').select({
          filterByFormula: stockCheckFormula,
          fields: ["Count"],
          maxRecords: 1
        }).firstPage();

        const stockAvailable = stockRecords.length > 0 ? (stockRecords[0].fields.Count as number) : 0;
        
        shopContractsDebug.stockChecks.push({
            resourceType: resourceToBuy,
            contractId: contract.id,
            stockQuery: stockCheckFormula,
            stockFound: stockAvailable
        });

        if (stockAvailable > 0) {
          retailFoodShopOffers.push({
            shopId: shopBuildingId,
            shopName: shopName,
            resourceType: resourceToBuy,
            price: price,
            quantityAvailable: stockAvailable, // Actual stock in shop
            contractId: contract.fields.ContractId || contract.id,
          });
        }
      }
      debugRetailFoodOffers.push(shopContractsDebug);
    }
    // Add debugRetailFoodOffers to a global debug object if needed, or return it separately
    return { offers: retailFoodShopOffers, debugLog: debugRetailFoodOffers };
  } catch (error) {
    console.error(`Error fetching retail food offers:`, error);
    // Optionally, add error to a global debug object
    return { offers: [], debugLog: [{ error: `Error fetching retail food offers: ${error}` }] };
  }
}


export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const citizenUsername = searchParams.get('citizenUsername');

  if (!citizenUsername) {
    return NextResponse.json({ success: false, error: 'citizenUsername parameter is required' }, { status: 400 });
  }

  const options: EatingOption[] = [];
  const debugInfo: Record<string, any> = {
    queries: {},
    results: {},
    foodResourceTypesUsed: FOOD_RESOURCE_TYPES,
  };

  try {
    const citizen = await fetchCitizenByName(citizenUsername);
    if (!citizen) {
      return NextResponse.json({ success: false, error: `Citizen ${citizenUsername} not found`, debug: debugInfo }, { status: 404 });
    }
    debugInfo.citizenRecord = citizen;
    const citizenDucats = (citizen.fields.Ducats as number) || 0;
    debugInfo.citizenDucats = citizenDucats;

    let citizenCoords: { lat: number; lng: number } | null = null;
    if (citizen.fields.Position && typeof citizen.fields.Position === 'string') {
      try {
        const pos = JSON.parse(citizen.fields.Position as string);
        if (typeof pos.lat === 'number' && typeof pos.lng === 'number') {
          citizenCoords = pos;
          debugInfo.citizenPosition = citizenCoords;
        }
      } catch (e) {
        console.warn(`[get-eating-options] Failed to parse citizen position for ${citizenUsername}: ${citizen.fields.Position}`);
        debugInfo.citizenPositionError = `Failed to parse: ${citizen.fields.Position}`;
      }
    } else {
      debugInfo.citizenPosition = "Not set or not a string.";
    }

    // 1. Check Inventory
    const inventoryResourceTypesFilter = FOOD_RESOURCE_TYPES.map(rt => `{Type} = '${escapeAirtableValue(rt)}'`);
    const inventoryOrFilter = `OR(${inventoryResourceTypesFilter.join(', ')})`;
    const inventoryFormula = `AND({AssetType} = 'citizen', {Asset} = '${escapeAirtableValue(citizenUsername)}', {Owner} = '${escapeAirtableValue(citizenUsername)}', ${inventoryOrFilter})`;
    debugInfo.queries.inventory = inventoryFormula;
    const inventoryResources = await airtable('RESOURCES').select({ filterByFormula: inventoryFormula }).all();
    const formattedInventoryResources = inventoryResources.map(r => ({ id: r.id, fields: r.fields }));
    debugInfo.results.inventory = formattedInventoryResources;

    formattedInventoryResources.forEach(res => {
      const quantity = (res.fields.Count as number) || 0;
      if (quantity > 0) {
        options.push({
          source: 'inventory',
          details: `${res.fields.Type} (Quantité: ${quantity.toFixed(1)})`,
          resourceType: res.fields.Type as string,
          quantity: quantity,
        });
      }
    });

    // 2. Check Home
    const homeBuilding = await fetchCitizenHome(citizenUsername);
    debugInfo.homeBuildingRecord = homeBuilding;
    if (homeBuilding && homeBuilding.fields.BuildingId) {
      const homeBuildingId = homeBuilding.fields.BuildingId as string;
      const homeBuildingName = homeBuilding.fields.Name as string || homeBuildingId;

      const homeResourceTypesFilter = FOOD_RESOURCE_TYPES.map(rt => `{Type} = '${escapeAirtableValue(rt)}'`);
      const homeOrFilter = `OR(${homeResourceTypesFilter.join(', ')})`;
      const homeResourcesFormula = `AND({AssetType} = 'building', {Asset} = '${escapeAirtableValue(homeBuildingId)}', {Owner} = '${escapeAirtableValue(citizenUsername)}', ${homeOrFilter})`;
      debugInfo.queries.homeResources = homeResourcesFormula;
      const homeResources = await airtable('RESOURCES').select({ filterByFormula: homeResourcesFormula }).all();
      const formattedHomeResources = homeResources.map(r => ({ id: r.id, fields: r.fields }));
      debugInfo.results.homeResources = formattedHomeResources;
      
      formattedHomeResources.forEach(res => {
        const quantity = (res.fields.Count as number) || 0;
        if (quantity > 0) {
          options.push({
            source: 'home',
            details: `${res.fields.Type} à ${homeBuildingName} (Quantité: ${quantity.toFixed(1)})`,
            resourceType: res.fields.Type as string,
            buildingId: homeBuildingId,
            buildingName: homeBuildingName,
            quantity: quantity,
          });
        }
      });
    }

    // 3. Check Taverns
    const tavernFoodOffersDebug: any[] = [];
    const tavernResourceTypeFilters = FOOD_RESOURCE_TYPES.map(rt => `{ResourceType} = '${escapeAirtableValue(rt)}'`);
    const tavernOrResourceTypeFilter = `OR(${tavernResourceTypeFilters.join(', ')})`;
    const tavernBuildingFormula = "AND(OR({Type}='tavern', {Type}='inn'), {IsConstructed}=TRUE())";
    debugInfo.queries.tavernBuildings = tavernBuildingFormula;
    const tavernRecords = await airtable('BUILDINGS').select({
      filterByFormula: tavernBuildingFormula,
      fields: ["BuildingId", "Name", "Type"]
    }).all();
    const formattedTavernRecords = tavernRecords.map(r => ({ id: r.id, fields: r.fields as FieldSet })); // Cast fields
    debugInfo.results.tavernBuildings = formattedTavernRecords.map(t => ({ // Log filtered taverns if citizenCoords was available
        id: t.fields.BuildingId, 
        name: t.fields.Name, 
        type: t.fields.Type,
        // @ts-ignore - distance might be added if filtered
        distance: citizenCoords && t.distance !== undefined ? t.distance.toFixed(1) + 'm' : 'N/A (no citizen pos or not filtered)'
    }));


    for (const tavern of formattedTavernRecords) { // Iterate over potentially filtered and distance-sorted taverns
      const tavernBuildingId = tavern.fields.BuildingId as string;
      const tavernName = (tavern.fields.Name as string) || tavernBuildingId;
      if (!tavernBuildingId) continue;

      const contractFormula = `AND({SellerBuilding} = '${escapeAirtableValue(tavernBuildingId)}', {Type} = 'public_sell', {Status} = 'active', ${tavernOrResourceTypeFilter})`;
      const foodContracts = await airtable('CONTRACTS').select({
        filterByFormula: contractFormula,
        fields: ["ResourceType", "PricePerResource", "TargetAmount", "ContractId"]
      }).all();
      const formattedFoodContracts = foodContracts.map(r => ({ id: r.id, fields: r.fields }));
      
      tavernFoodOffersDebug.push({
        tavernId: tavernBuildingId,
        tavernName: tavernName,
        query: contractFormula,
        results: formattedFoodContracts,
      });

      for (const contract of foodContracts) {
        const offer = {
          tavernId: tavernBuildingId,
          tavernName: tavernName,
          resourceType: contract.fields.ResourceType as string,
          price: contract.fields.PricePerResource as number,
          quantityAvailable: contract.fields.TargetAmount as number,
          contractId: (contract.fields.ContractId || contract.id) as string,
        };
        if (citizenDucats >= (offer.price || 0)) {
          options.push({
            source: 'tavern',
            details: `${offer.resourceType} à ${offer.tavernName} (Prix: ${offer.price || 0} Ducats, Disponible: ${(offer.quantityAvailable || 0).toFixed(1)})`,
            resourceType: offer.resourceType,
            buildingId: offer.tavernId,
            buildingName: offer.tavernName,
            price: offer.price,
            quantity: offer.quantityAvailable,
            contractId: offer.contractId,
          });
        } else {
           options.push({
            source: 'tavern',
            details: `${offer.resourceType} à ${offer.tavernName} (Prix: ${offer.price || 0} Ducats, Disponible: ${(offer.quantityAvailable || 0).toFixed(1)}) - Fonds insuffisants`,
            resourceType: offer.resourceType,
            buildingId: offer.tavernId,
            buildingName: offer.tavernName,
            price: offer.price,
            quantity: offer.quantityAvailable,
            contractId: offer.contractId,
          });
        }
      }
    }
    // debugInfo.tavernFoodChecks = tavernFoodOffersDebug; // Removed this line
    debugInfo.results.tavernFoodOffers = tavernFoodOffersDebug; // Log the raw offers from taverns

    // 4. Check Retail Food Shops
    const retailFoodOffersResult = await fetchRetailFoodOffers(FOOD_RESOURCE_TYPES, citizenCoords, MAX_CLOSEST_PROVIDERS_PER_TYPE);
    const retailFoodShopOffers = retailFoodOffersResult.offers;
    // debugInfo.retailFoodShopProcessingDetails = retailFoodOffersResult.debugLog; // Removed this line
    debugInfo.retailFoodShopDebugLog = retailFoodOffersResult.debugLog; // Log the debug from retail shops

    // Mappage simplifié pour debugInfo.results.retailFoodShops
    debugInfo.results.retailFoodShops = retailFoodShopOffers.map(offer => ({
        shopName: offer.buildingName, // Utiliser buildingName pour la cohérence
        resourceType: offer.resourceType,
        price: offer.price,
        quantity: offer.quantity
    }));

    retailFoodShopOffers.forEach(offer => {
      // L'offre contient déjà les champs nécessaires, y compris buildingId, buildingName, etc.
      // La vérification des fonds est faite ici pour l'affichage, mais l'option est ajoutée quand même.
      const detailsSuffix = citizenDucats >= (offer.price || 0) ? "" : " - Fonds insuffisants";
      options.push({
        ...offer, // Inclut source, resourceType, buildingId, buildingName, price, quantity, contractId
        details: `${offer.resourceType} chez ${offer.buildingName} (Prix: ${offer.price || 0} Ducats, Stock: ${(offer.quantity || 0).toFixed(1)})${detailsSuffix}`,
      });
    });


    return NextResponse.json({ success: true, citizenUsername, options });

  } catch (error: any) {
    console.error(`[API get-eating-options] Error for ${citizenUsername}:`, error);
    // debugInfo might not be fully populated in case of an early error, so it's better to not include it here either.
    return NextResponse.json({ success: false, error: error.message || 'Failed to fetch eating options' }, { status: 500 });
  }
}
