import os
import openai
import concurrent.futures
import pandas as pd
import logging
import copy

from typing import Dict, List, Optional

from dotenv import load_dotenv
from src import ChatGPTCrawler

logger = logging.getLogger('main')

PROMPT_TEMPLATE_FIND_CONTACTS = """
         I am trying to find the people responsible for transport policy on a website.
         If they are found, they should be saved.
         Usually there are several people on a site and they belong to one party.
         If you have found the right website, then I would like to have exactly one person from each party.
         Here is the url: {url}
        """

PROMPT_TEMPLATE_UPDATE_CONTACTS = """
        I am trying to find information about this person on a website.
        When you have found the information, you want it to be saved.
        Here is the person: {person} and the url: {contact_url}
        """


def setup():
    """
    Inits the openai api key from .env file and setups the logger
    """
    load_dotenv()
    openai.api_key = os.getenv("OPENAI_API_KEY")

    logger.setLevel(logging.INFO)

    # Create handlers (e.g., console handler)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # Create formatters and add it to handlers
    formatter = logging.Formatter('%(levelname)s:%(message)s')
    console_handler.setFormatter(formatter)

    # Add handlers to the logger
    logger.addHandler(console_handler)


def check_for_subpages(contacts: List[Dict[str, Optional[str]]]):
    """
    Checks if one contact from the list is missing a contacts_url and if contacts is empty

    Returns: True if every contact in the list has an url
    """
    contacts_tmp = copy.deepcopy(contacts)
    for contact in contacts_tmp:
        if contact['contact_url'] is None:
            logger.warning('Für den Kontakt ' + contact['name'] + 'wurde keine Unterseite gefunden. ')
            contacts_tmp.remove(contact)
    return contacts_tmp


def deduplicate_contacts(contacts: List[Dict[str, Optional[str]]]):
    """
    Removes all duplicate contacts from a list by Name

    Return: The changed list of contacts
    """
    contacts_set = set()
    unique_contacts = []

    for contact in contacts:
        if contact['name'] not in contacts_set:
            unique_contacts.append(contact)
            contacts_set.add(contact['name'])

    return unique_contacts


def replace_none_with_unbekannt(
        contacts: List[Dict[str, Optional[str]]]
) -> List[Dict[str, str]]:
    """
    Replaces every None value in a list with "Unbekannt"

    Returns: the changed list
    """
    for contact in contacts:
        for key in contact:
            if contact[key] is None:
                contact[key] = "Unbekannt"
    return contacts


def merge_contact_lists(
        list1: List[Dict[str, Optional[str]]],
        list2: List[Dict[str, Optional[str]]],
) -> List[Dict[str, Optional[str]]]:
    """
    Merges 2 lists together in way that no information is lost
    When the same field in the 2 lists has different values it merges them into a new list and
    separates them with ' | '
    """
    merged_contacts = {}

    for contact in list1:
        name = contact['name']
        merged_contacts[name] = contact

    for contact in list2:
        name = contact['name']
        if name in merged_contacts:
            for key, value in contact.items():
                if key != 'name' and value is not None:
                    existing_value = merged_contacts[name].get(key)
                    if existing_value and existing_value != value:
                        merged_contacts[name][key] = existing_value + ' | ' + value
                    else:
                        merged_contacts[name][key] = value
        else:
            merged_contacts[name] = contact

    return list(merged_contacts.values())


def find_contacts(url: str) -> List[Dict[str, str]]:
    """
    Main logic to find a contact
    """
    debug = False
    client = ChatGPTCrawler(debug)
    client.attach(update)
    contacts = client.start(PROMPT_TEMPLATE_FIND_CONTACTS, url=url)
    logger.info(f"Tokens used: input {client.input_tokens_used}, output {client.output_tokens_used}")
    logger.info("Found contacts:")
    logger.info(contacts)

    contacts_from_first_search = copy.deepcopy(deduplicate_contacts(contacts))

    if not contacts:
        logger.info("Bei der Suche für die Seite " + url + " wurden keine Kontakte gefunden")
        return contacts
    logger.info("Bei der initialen Suche wurden folgende Kontakte gefunden:")
    contacts_copy = copy.deepcopy(contacts)
    replace_none_with_unbekannt(contacts_copy)
    for contact in contacts_copy:
        logger.info(f"Name: {contact['name']}, "
                    f"Partei: {contact['political_party']}, "
                    f"Position: {contact['position']}, "
                    f"Email: {contact['email']}, "
                    f"Telefon: {contact['phone']}, "
                    f"Website: {contact['contact_url']}, "
                    f"Adresse: {contact['address']}, "
                    f"Zusätzliche Infos: {contact['additional_info']}")

    # check if every contact in contacts has a contact_url
    contacts_tmp = copy.deepcopy(check_for_subpages(contacts))
    if contacts_tmp:
        client.reset()
        update_contacts(contacts_tmp)
        contacts.extend(contacts_tmp)
        contacts = deduplicate_contacts(contacts)
        merge_contact_lists(contacts_from_first_search, contacts)
    return contacts


def update_contacts(
        contacts: List[Dict[str, Optional[str]]]
) -> List[Dict[str, Optional[str]]]:
    """
    Looks for further contact information on a given subpage

    Return: a List with all updated contacts
    """
    logger.info("Unterseiten werden jetzt für zusätzliche Informationen durchsucht.")
    contacts_list = []

    # optionally limit number of Threads with max_workers=x
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        future_to_contact = {executor.submit(update_contact, contact): contact for contact in contacts}
        for future in concurrent.futures.as_completed(future_to_contact):
            for contact in future.result():
                contacts_list.append(contact)
    return contacts_list


def update_contact(contact: Dict[str, Optional[str]]) -> List[Dict[str, Optional[str]]]:
    """
    Creates a new client and looks for a single contact on a subpage using the PROMPT_TEMPLATE_UPDATE_CONTACTS

    Returns: a single contact
    """
    client = ChatGPTCrawler()
    client.attach(update)
    detailed_contact = client.start(
        PROMPT_TEMPLATE_UPDATE_CONTACTS,
        person=contact["name"],
        contact_url=contact["contact_url"],
    )
    logger.info(detailed_contact)
    return detailed_contact


def update(state):
    """
    Listener to get the called url from the client for display in ui and logger
    """
    if state is not None:
        the_url = state
        logger.info('Rufe ' + str(the_url) + ' auf.')


def run(urls: List[str]) -> pd.DataFrame:
    """
    Starts the search for contacts on the given urls
    will return a pandas dataframe with all contacts found
    """

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(find_contacts, url) for url in urls]

    contacts = []
    for future in concurrent.futures.as_completed(futures):
        try:
            result = future.result()
            contacts.extend(result)
        except Exception as e:
            logger.error(f"Beim durchsuchen ist folgender Fehler aufgetreten: {e}")

    if not contacts:
        logger.info("Keine Kontakte gefunden.")

    replace_none_with_unbekannt(contacts)

    for contact in contacts:
        logger.info(f"Name: {contact['name']}, "
                    f"Partei: {contact['political_party']}, "
                    f"Position: {contact['position']}, "
                    f"Email: {contact['email']}, "
                    f"Telefon: {contact['phone']}, "
                    f"Website: {contact['contact_url']}, "
                    f"Adresse: {contact['address']}, "
                    f"Zusätzliche Infos: {contact['additional_info']}")

    df = pd.DataFrame(contacts)
    df['last_updated'] = pd.Timestamp.now()
    return df


def run_df(df: pd.DataFrame) -> pd.DataFrame:
    # look at unique start links (start_url) column
    urls = df.start_url.unique()
    # run
    df = run(urls)
    return df


def merge_original_and_updated_df(original_df: pd.DataFrame, updated_df: pd.DataFrame) -> pd.DataFrame:
    """
    Merges the original and updated contact dataframes together, ensuring that updated_df rows appear before original_df rows
    for each unique start_url. Then, sorts the merged dataframe by 'start_url'.
    """
    # Add a temporary column to indicate the source of each row
    original_df['source'] = 1  # 1 indicates rows from the original dataframe
    updated_df['source'] = 0  # 0 indicates rows from the updated dataframe

    # Merge the dataframes
    merged_df = pd.concat([original_df, updated_df], ignore_index=True)

    # Drop duplicates based on 'name' and 'start_url', keeping the last occurrence
    merged_df = merged_df.drop_duplicates(subset=['name', 'start_url'], keep='last')

    # Sort by 'start_url' and then by 'source' to ensure updated_df rows appear first
    merged_df = merged_df.sort_values(by=['start_url', 'source'])

    # Optionally, remove the temporary 'source' column if it's no longer needed
    merged_df = merged_df.drop(columns=['source'])

    return merged_df


if __name__ == "__main__":
    setup()
    original_df = pd.read_csv("./contacts.csv")
    updated_df = run_df(original_df)
    updated_df.to_csv("./contacts_updated.csv", index=False, encoding="utf-8-sig")
    merged_df = merge_original_and_updated_df(original_df, updated_df)
    merged_df.to_csv("./contacts_merged.csv", index=False, encoding="utf-8-sig")
