describe("site", () => {
  it("has a home page with a title and heading", () => {
    cy.readFile("site/index.html").then((html) => {
      const doc = new DOMParser().parseFromString(html, "text/html");
      expect(doc.title).to.contain("Steven M. Cohn");
      expect(doc.querySelector("h1").textContent).to.contain("Steven M. Cohn");
    });
  });
});
