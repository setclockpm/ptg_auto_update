// index.js (completely empty)
import "./styles.css";
import data from './data.js'

const returmSearchResults = (field) => {
  // Create elements needed to build a table
  const table = document.createElement('table')
  // Append newly created elements into the DOM
  const results = document.querySelector('div#results');
  // onSubmit
  results.append(table)
  // Set content and attributes
  a.innerHTML = field.COSName
  a.setAttribute('href', field.COSDesc)
  img.setAttribute('src', field.PDIName)
  div.setAttribute('class', 'card')
}



